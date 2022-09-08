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

Only the OTLP over gRPC exporter is currently supported.

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

* https://docs.pytest.org/en/6.2.x/writing_plugins.html
* https://docs.pytest.org/en/6.2.x/reference.html#hooks

These are extremely helpful in understanding the lifecycle of a pytest run.

To get setup for development, you will likely want to use a "virtual environment", using
great tools like `virtualenv` or `pyenv`.

Once you have a virtual environment, install this package for editing, along with its
development dependencies, with this command:

```bash
pip install -e '.[dev]'
```

When sending pull requests, don't forget to bump the version in
[setup.cfg](./setup.cfg).
