# pytest-opentelemetry

Instruments your pytest runs, exporting the spans and timing via OpenTelemetry.

## Installation and Usage

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

## Visualizing Test Traces

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
