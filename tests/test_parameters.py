import pytest
from _pytest.pytester import Pytester

from . import SpanRecorder


def test_parametrize_arguments_become_attributes(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        import pytest

        class Thing:
            def __repr__(self):
                return 'Thing()'

        @pytest.mark.parametrize(
            'text, number, ratio, flag, thing',
            [('bearer ', 7, 0.5, True, Thing())],
        )
        def test_one(text, number, ratio, flag, thing):
            pass
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    node = "test_parametrize_arguments_become_attributes.py::test_one"
    for name in (node, f"{node}::setup", f"{node}::call", f"{node}::teardown"):
        attributes = spans[name].attributes
        assert attributes
        assert attributes["pytest.param.text"] == "bearer "
        assert attributes["pytest.param.number"] == 7
        assert attributes["pytest.param.ratio"] == 0.5
        assert attributes["pytest.param.flag"] is True
        assert attributes["pytest.param.thing"] == "Thing()"


def test_unparametrized_tests_have_no_parameter_attributes(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        def test_one():
            pass
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    attributes = spans[
        "test_unparametrized_tests_have_no_parameter_attributes.py::test_one"
    ].attributes
    assert attributes
    assert not [key for key in attributes if key.startswith("pytest.param.")]


def test_indirect_parameters_become_attributes(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        import pytest

        @pytest.fixture(params=['red', 'blue'])
        def color(request):
            return request.param

        def test_one(color):
            pass
    """)
    pytester.runpytest().assert_outcomes(passed=2)

    nodeid = "test_indirect_parameters_become_attributes.py::test_one"
    spans = span_recorder.spans_by_nodeid(nodeid)
    for color in ("red", "blue"):
        attributes = spans[f"{nodeid}[{color}]"].attributes
        assert attributes
        assert attributes["pytest.param.color"] == color


def test_long_values_are_truncated_in_the_middle(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        import pytest

        @pytest.mark.parametrize(
            'text, items, exact',
            [('a' * 100 + 'b' * 100, list(range(200)), 'c' * 120)],
            ids=['long'],
        )
        def test_one(text, items, exact):
            pass
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    attributes = spans[
        "test_long_values_are_truncated_in_the_middle.py::test_one"
    ].attributes
    assert attributes

    text = attributes["pytest.param.text"]
    assert isinstance(text, str)
    assert len(text) == 120
    assert text == "a" * 60 + "…" + "b" * 59

    items = attributes["pytest.param.items"]
    assert isinstance(items, str)
    assert len(items) == 120
    assert items.startswith("[0, 1, 2, ")
    assert "…" in items
    assert items.endswith(", 198, 199]")

    assert attributes["pytest.param.exact"] == "c" * 120


def test_tavern_parameters_become_attributes(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    # tavern's YAML test items keep their parameters in `parametrize_vars`.
    pytester.makeconftest("""
        import pytest

        class YamlItem(pytest.Item):
            def runtest(self):
                pass

        class YamlFile(pytest.File):
            def collect(self):
                item = YamlItem.from_parent(self, name='get user[alice]')
                item.parametrize_vars = {'user': 'alice', 'status': 200}
                yield item

        def pytest_collect_file(parent, file_path):
            if file_path.suffix == '.yaml':
                return YamlFile.from_parent(parent, path=file_path)
    """)
    pytester.makefile(".yaml", test_users="")
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    attributes = spans["test_users.yaml::get user[alice]"].attributes
    assert attributes
    assert attributes["pytest.param.user"] == "alice"
    assert attributes["pytest.param.status"] == 200


def test_parametrize_arguments_have_no_fixture_spans(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    # pytest gives each argument of a parametrized test to the test through a
    # fixture of its own, which only returns the argument.
    pytester.makepyfile("""
        import pytest

        @pytest.fixture
        def real():
            pass

        @pytest.mark.parametrize('header', ['bearer '])
        def test_one(header, real):
            pass
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    assert "real setup" in spans
    assert "real teardown" in spans
    assert "header setup" not in spans
    assert "header teardown" not in spans


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            """
            import pytest

            @pytest.fixture(params=[111, 222])
            def number(request):
                return request.param

            def test_one(number):
                pass
            """,
            id="params-of-the-fixture",
        ),
        pytest.param(
            """
            import pytest

            @pytest.fixture
            def number(request):
                return request.param

            @pytest.mark.parametrize('number', [111, 222], indirect=True)
            def test_one(number):
                pass
            """,
            id="indirect-parameters-of-the-test",
        ),
    ],
)
@pytest.mark.parametrize("name", ["number setup", "number teardown"])
def test_fixture_parameters_become_attributes(
    pytester: Pytester, span_recorder: SpanRecorder, source: str, name: str
) -> None:
    pytester.makepyfile(source)
    pytester.runpytest().assert_outcomes(passed=2)

    spans = span_recorder.spans_named(name)
    numbers = [(span.attributes or {})["pytest.param.number"] for span in spans]
    assert len(numbers) == 2
    assert 111 in numbers
    assert 222 in numbers


def test_unparametrized_fixtures_have_no_parameter_attributes(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        import pytest

        @pytest.fixture
        def plain():
            pass

        def test_one(plain):
            pass
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    attributes = span_recorder.spans_by_name()["plain setup"].attributes
    assert attributes
    assert not [key for key in attributes if key.startswith("pytest.param.")]
