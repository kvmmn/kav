"""Tests for HTTP/OpenAPI adapter projection (D-026)."""
import pytest

from kav_sdk import (
    Change, Constraints, Domain, EvaluatorDecl, ExperimentResult, ExperimentSpec,
    Evidence, Objective, Parameter, ProjectManifest, SearchSpace,
)
from kav_sdk.adapter import HostAdapter, HostRunner, SimulatedHost
from kav_sdk.http import AdapterServer, HttpHostAdapter, load_openapi
from kav_sdk.memory import ProjectMemory
from kav_sdk.tools import make_kav_tools


@pytest.fixture()
def mem(tmp_path):
    m = ProjectMemory(tmp_path, "numerai-demo")
    yield m
    m.close()


def manifest():
    return ProjectManifest(
        project_id="numerai-demo", name="Demo",
        objective=Objective(metric="correlation", direction="maximize", baseline=0.021),
        constraints=Constraints(max_budget_per_experiment={"max_compute_hours": 2}),
        evaluator=EvaluatorDecl(owned_by="host"),
    )


def space():
    return SearchSpace(
        project_id="numerai-demo",
        parameters=[Parameter(name="lr", type="number",
                              domain=Domain(kind="range", min=0.001, max=0.1))],
        defaults={"lr": 0.01},
    )


def spec(eid="exp-http01", lr=0.02):
    return ExperimentSpec(
        experiment_id=eid, project_id="numerai-demo", hypothesis_id="hyp-http01",
        changes=[Change(parameter="lr", value=lr)],
        reproducibility={"seed": 42},
    )


def true_metric(params):
    lr = params["lr"]
    return 0.021 + 0.9 * lr - 15.0 * (lr - 0.03) ** 2


def test_openapi_names_the_four_operations():
    doc = load_openapi()
    assert doc["openapi"].startswith("3.0")
    assert doc["info"]["version"] == "0.1"
    paths = doc["paths"]
    assert "get" in paths["/v0.1/manifest"]
    assert "get" in paths["/v0.1/search-space"]
    assert "post" in paths["/v0.1/experiments"]
    assert "post" in paths["/v0.1/results"]
    exp_ref = paths["/v0.1/experiments"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert exp_ref.endswith("experiment-spec.schema.json")


def test_http_host_satisfies_protocol():
    inner = SimulatedHost(manifest(), space(), true_metric)
    with AdapterServer(inner) as srv:
        remote = HttpHostAdapter(srv.base_url)
        assert isinstance(remote, HostAdapter)
        assert remote.manifest().name == "Demo"
        assert remote.search_space().defaults == {"lr": 0.01}


def test_http_run_and_report_roundtrip():
    inner = SimulatedHost(manifest(), space(), true_metric)
    with AdapterServer(inner) as srv:
        remote = HttpHostAdapter(srv.base_url)
        result = remote.run_experiment(spec())
        assert result.status.value == "completed"
        assert result.evidence.metric_value == pytest.approx(true_metric({"lr": 0.02}))
        echoed = remote.report_result(result)
        assert echoed.experiment_id == result.experiment_id


def test_http_openapi_endpoint_served():
    inner = SimulatedHost(manifest(), space(), true_metric)
    with AdapterServer(inner) as srv:
        from http.client import HTTPConnection
        from urllib.parse import urlparse
        parsed = urlparse(srv.base_url)
        conn = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        conn.request("GET", "/v0.1/openapi.json")
        resp = conn.getresponse()
        assert resp.status == 200
        body = resp.read().decode("utf-8")
        conn.close()
        assert "/v0.1/experiments" in body


def test_http_invalid_spec_is_400():
    inner = SimulatedHost(manifest(), space(), true_metric)
    with AdapterServer(inner) as srv:
        from http.client import HTTPConnection
        from urllib.parse import urlparse
        parsed = urlparse(srv.base_url)
        conn = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        conn.request(
            "POST", "/v0.1/experiments",
            body=b'{"not": "a spec"}',
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        assert resp.status == 400
        body = resp.read().decode("utf-8")
        conn.close()
        assert "invalid_spec" in body


def test_host_runner_drains_over_http(mem):
    inner = SimulatedHost(manifest(), space(), true_metric)
    with AdapterServer(inner) as srv:
        runner = HostRunner(mem, HttpHostAdapter(srv.base_url))
        runner.attach()
        tools = {t.__name__: t for t in make_kav_tools(mem)}
        assert tools["issue_spec"](spec("exp-http10", lr=0.02).model_dump_json()).startswith("ISSUED")
        assert runner.drain_pending() == 1
        row = mem.get_experiment("exp-http10")
        assert row["status"] == "completed"
        assert row["metric_value"] == pytest.approx(true_metric({"lr": 0.02}))
        assert mem.pending_specs() == []


def test_http_failed_run_is_ingested(mem):
    def boom(_params):
        raise RuntimeError("evaluator crashed")

    inner = SimulatedHost(manifest(), space(), boom)
    with AdapterServer(inner) as srv:
        runner = HostRunner(mem, HttpHostAdapter(srv.base_url))
        runner.attach()
        tools = {t.__name__: t for t in make_kav_tools(mem)}
        tools["issue_spec"](spec().model_dump_json())
        assert runner.drain_pending() == 1
        row = mem.get_experiment("exp-http01")
        assert row["status"] == "failed"
        assert mem.pending_specs() == []
