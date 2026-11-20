# pytest-opentelemetry

Instruments your pytest runs, exporting the spans and timing via OpenTelemetry.

## Why instrument my test suite?

As projects grow larger, perhaps with many contributors, test suite runtime can be
a significant limiting factor to how fast you and your team can deliver changes.  By
measuring your test suite's runtime in detail, and keeping a history of this runtime
in a visualization tool like [Jaeger](https://jaegertracing.io), you can spot
test bottlenecks that might be slowing your entire suite down.

Additionally, `pytest` makes an excellent driver for _integration_ tests that operate
on fully deployed systems, like your testing/staging environment.  By using
`pytest-opentelemetry` and configuring the appropriate propagators, you can connect
traces from your integration test suite to your running system to analyze failures
more quickly.

Even if you only enable `pytest-opentelemetry` locally for occasional debugging, it
can help you understand _exactly_ what is slowing your test suite down.  Did you
forget to mock that `requests` call?  Didn't realize the test suite was creating
10,000 example accounts?  Should that database setup fixture be marked
`scope=module`? These are the kinds of questions `pytest-opentelemetry` can help
you answer.

`pytest-opentelemetry` works even better when testing applications and libraries that
are themselves instrumented with OpenTelemetry.  This will give you deeper visibility
into the layers of your stack, like database queries and network requests.

## Installation and usage

```bash
pip install pytest-opentelemetry
```

`pytest-opentelemetry` needs Python 3.11 or later, pytest 8.0.0 or later, and version
1.28.0 or later of the OpenTelemetry API and SDK.

Installing a library that exposes a specific pytest-related entry point is automatically
loaded as a pytest plugin.  Simply installing the plugin should be enough to register
it for pytest.

Using the `--export-traces` flag enables trace exporting (otherwise, the created spans
will only be tracked in memory):

```bash
pytest --export-traces
```

By default, this exports traces to `http://localhost:4317`, which will work well if
you're running a local [OpenTelemetry
Collector](https://opentelemetry.io/docs/collector/) exposing the OTLP gRPC interface.
You can use any of the [OpenTelemetry environment
variables](https://opentelemetry-python.readthedocs.io/en/latest/sdk/environment_variables.html)
to adjust the tracing export or behavior:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://another.collector:4317
pytest --export-traces
```

OTLP over gRPC is the default exporter, and the only one that `pytest-opentelemetry`
installs.  To use another, install its package and name it in `OTEL_TRACES_EXPORTER`,
as you would for any OpenTelemetry SDK.  For example, to export OTLP over HTTP:

```bash
pip install opentelemetry-exporter-otlp-proto-http
export OTEL_TRACES_EXPORTER=otlp_proto_http
export OTEL_EXPORTER_OTLP_ENDPOINT=http://another.collector:4318
pytest --export-traces
```

To describe where the tests ran, install the `container` extra.  It adds
[`opentelemetry-container-distro`](https://pypi.org/project/opentelemetry-container-distro/),
and `pytest-opentelemetry` then records the `process.*` attributes of the pytest
process, and the Docker container and Kubernetes pod when it runs in one:

```bash
pip install 'pytest-opentelemetry[container]'
```

`pytest-opentelemetry` will use the name of the project's directory as the OpenTelemetry
`service.name`, but it will also respect the standard `OTEL_SERVICE_NAME` and
`OTEL_RESOURCE_ATTRIBUTES` environment variables.  If you would like to permanently
specify those for your project, consider using the very helpful
[`pytest-env`](https://pypi.org/project/pytest-env/) package to set these for all test
runs, for example, in your `pyproject.toml`:

```toml
[tool.pytest.ini_options]
env = [
    "OTEL_RESOURCE_ATTRIBUTES=service.name=my-project",
]
```

If you are using the delightful [`pytest-xdist`](https://pypi.org/project/pytest-xdist/)
package to spread your tests out over multiple processes or hosts,
`pytest-opentelemetry` will automatically unite them all under one trace.  If this
`pytest` run is part of a larger trace, you can provide a `--trace-parent` argument to
nest this run under that parent:

```bash
pytest ... --trace-parent 00-1234567890abcdef1234567890abcdef-fedcba0987654321-01
```

## The spans of a test run

A test run is one trace.  Its root is a span named `test run`, and its children are a
`collection` span, a span for each test, and the spans of the fixtures that tests share:

```
test run
├─ collection
├─ database setup                                a fixture that tests share
├─ tests/test_api.py::test_health
│  ├─ tests/test_api.py::test_health::setup
│  │  └─ client setup                            a fixture of this test
│  ├─ tests/test_api.py::test_health::call
│  └─ tests/test_api.py::test_health::teardown
│     └─ client teardown
└─ database teardown
```

Each fixture has a `<name> setup` span and a `<name> teardown` span.  The spans that your
code creates while a fixture sets up or tears down are children of those spans.

The spans of a fixture that pytest sets up for one test are inside that test.  The spans
of a fixture that tests share are children of the test run.  pytest sets up a shared
fixture during the first test that uses it, and tears it down during the last, but
neither test's span includes that time: a test's span starts after pytest has set up
those fixtures, and ends when pytest has torn down the test itself, before it tears them
down.  The duration of a test is then the time of the test and of its own fixtures,
wherever the test falls in its module.

What a fixture's scope says and what pytest does can differ.  pytest sets up a
class-scoped fixture for every test that is not in a class, and it sets up a fixture for
every test that parametrizes it along with a plain argument.  The spans of those
fixtures are inside each test.

A fixture whose setup raises records the exception on its setup span, and on the span of
the test that asked for it.  An error in a fixture's teardown is recorded only on the
span of the test that pytest reports it for.

Some things do not follow that layout:

* A shared fixture that pytest sets up after one of the test's own fixtures sets up in
  the middle of that test.  Its setup span is inside the test, and its time counts
  toward the test's duration.  This happens to a fixture that a test first asks for with
  `request.getfixturevalue()`, and to a fixture that another fixture of the same name
  overrides and depends on.
* A finalizer that is added to a fixture after the fixture has set up, like the one a
  factory fixture adds each time a test calls it, runs before that fixture's teardown
  span starts.  For a shared fixture it runs as a child of the test run, outside of any
  test.
* The spans that a `pytest_runtest_setup` or `pytest_runtest_logstart` hook creates are
  children of the test run.  The test's span covers their time, but it does not exist
  yet when pytest calls those hooks.
* With [`pytest-asyncio`](https://pypi.org/project/pytest-asyncio/), the spans that an
  async fixture creates while it tears down are children of its setup span, because
  the fixture resumes in the context it set up in.

With `--trace-per-test` there is no `test run` span.  Each test is the root of a trace
of its own, and so is everything that is a child of the test run above: each setup and
each teardown of a shared fixture, and each span from one of those hooks.  When there
is a `--trace-parent`, they are children of that parent instead.

## Parametrized tests

The tests that pytest makes from one parametrized function share a span name, which is
the node ID without the ID of the parameters, like `tests/test_api.py::test_login`.  A
tool that groups spans by name then reports them together.  The `pytest.nodeid`
attribute of each span has the whole node ID, like
`tests/test_api.py::test_login[bearer]`.

The spans of a parametrized test have each of its parameters as an attribute named
`pytest.param.<name>`, from `@pytest.mark.parametrize`, a fixture's `params`, or a
[tavern](https://pypi.org/project/tavern/) test's `parametrize` mark.  A string, a
boolean, or a number keeps its value, and any other value becomes its `repr()`.  A value
longer than 120 characters keeps its start and its end, with `…` in place of the middle.

The setup and teardown spans of a fixture with a parameter have the same name for every
parameter, and have the parameter as `pytest.param.<name of the fixture>`.

## Working with other plugins

`pytest-opentelemetry` registers the object that creates its spans under the name
`opentelemetry`.  Another plugin or a `conftest.py` can get it from pytest's plugin
manager, for example to read the span for the whole test run:

```python
def pytest_collection_finish(session):
    plugin = session.config.pluginmanager.get_plugin("opentelemetry")
    trace_id = plugin.session_span.get_span_context().trace_id
```

With `--trace-per-test` there is no span for the whole run, so `session_span` is not
set.

## Tests that freeze time

If [`freezegun`](https://pypi.org/project/freezegun/) is installed,
`pytest-opentelemetry` adds `opentelemetry` and `pytest_opentelemetry` to freezegun's
list of ignored packages.  Spans then start and end at the real time, even while a test
has time frozen, so their durations stay correct.  This covers every span that
OpenTelemetry records during the test run, including the ones your application creates.

## Visualizing test traces

One quick way to visualize test traces would be to use an [OpenTelemetry
Collector](https://opentelemetry.io/docs/collector/) feeding traces to
[Jaeger](https://jaegertracing.io).  This can be configured with a minimal Docker
Compose file like:

```yaml
version: "3.8"
services:
  jaeger:
    image: jaegertracing/all-in-one:1.33
    ports:
    - 16686:16686    # frontend
    - 14250:14250    # model.proto
  collector:
    image: otel/opentelemetry-collector-contrib:0.49.0
    depends_on:
    - jaeger
    ports:
    - 4317:4317      # OTLP (gRPC)
    volumes:
    - ./otelcol-config.yaml:/etc/otelcol-contrib/config.yaml:ro
```

With this `otelcol-config.yaml`:

```yaml
receivers:
  otlp:
    protocols:
      grpc:

processors:
  batch:

exporters:
  jaeger:
    endpoint: jaeger:14250
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [jaeger]
```

## Developing

Two references I keep returning to is the pytest guide on writing plugins, and the
pytest API reference:

* https://docs.pytest.org/en/stable/how-to/writing_plugins.html
* https://docs.pytest.org/en/stable/reference/reference.html#hooks

These are extremely helpful in understanding the lifecycle of a pytest run.

To get set up for development, install [uv](https://docs.astral.sh/uv/), then install
this package and its development tools into a virtual environment, and install the git
hooks:

```bash
uv sync
uv run prek install
```

Run the tests and the checks with:

```bash
uv run pytest
uv run prek run --all-files
```

`hatch-vcs` gets the version from the git tags, so pull requests do not
change a version anywhere.
