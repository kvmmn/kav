"""Tests for the project-local memory layer."""
import pytest

from kav_sdk import (
    Budget, Change, Constraints, Domain, EvaluatorDecl, ExperimentResult,
    ExperimentSpec, Evidence, FindingKind, Objective, Parameter, PolicyDecl,
    ProjectManifest, ResearchFinding, SearchSpace,
)
from kav_sdk.memory import (
    DESK_MINIMAL, DESK_RICH_DIGEST, PROMOTION_AUTO_GUARDED, PROMOTION_MANUAL,
    ProjectMemory,
)


@pytest.fixture()
def mem(tmp_path):
    m = ProjectMemory(tmp_path, "numerai-demo")
    yield m
    m.close()


def manifest():
    return ProjectManifest(
        project_id="numerai-demo", name="Demo",
        objective=Objective(metric="correlation", direction="maximize"),
        constraints=Constraints(max_budget_per_experiment=Budget(max_compute_hours=2)),
        evaluator=EvaluatorDecl(owned_by="host"),
    )


def space():
    return SearchSpace(
        project_id="numerai-demo",
        parameters=[Parameter(name="lr", type="number",
                              domain=Domain(kind="range", min=0.001, max=0.1))],
        defaults={"lr": 0.01},
    )


def spec(eid="exp-aaa111", lr=0.02, seed=42):
    return ExperimentSpec(
        experiment_id=eid, project_id="numerai-demo", hypothesis_id="hyp-bbb222",
        changes=[Change(parameter="lr", value=lr)],
        reproducibility={"seed": seed},
    )


def result(eid="exp-aaa111", value=0.025):
    return ExperimentResult(experiment_id=eid, status="completed",
                            evidence=Evidence(metric_value=value))


def finding(fid="fnd-ccc333", kind="confirmed", conf=0.5):
    return ResearchFinding(
        finding_id=fid, project_id="numerai-demo", experiment_id="exp-aaa111",
        kind=kind, statement="Raising lr to 0.02 improved correlation.",
        confidence=conf, tags=["lr"],
    )


# ---- Law 4: project isolation
def test_memory_rejects_foreign_records(mem):
    foreign = manifest().model_copy(update={"project_id": "other-proj"})
    with pytest.raises(ValueError, match="Law 4"):
        mem.save_manifest(foreign)


# ---- roundtrips
def test_manifest_and_space_roundtrip(mem):
    mem.save_manifest(manifest())
    mem.save_search_space(space())
    assert mem.get_manifest().objective.metric == "correlation"
    assert mem.get_search_space().defaults == {"lr": 0.01}


def test_spec_result_flow(mem):
    mem.save_spec(spec())
    mem.save_result(result())
    row = mem.get_experiment("exp-aaa111")
    assert row["status"] == "completed"
    assert row["metric_value"] == 0.025


def test_result_requires_known_experiment(mem):
    with pytest.raises(KeyError):
        mem.save_result(result("exp-unknown"))


def test_pending_specs_fifo_until_result(mem):
    assert mem.pending_specs() == []
    mem.save_spec(spec("exp-pend01"))
    mem.save_spec(spec("exp-pend02"))
    assert [s.experiment_id for s in mem.pending_specs()] == ["exp-pend01", "exp-pend02"]
    mem.save_result(result("exp-pend01"))
    assert [s.experiment_id for s in mem.pending_specs()] == ["exp-pend02"]
    mem.save_result(result("exp-pend02", value=0.03))
    assert mem.pending_specs() == []


# ---- Law 3: findings immutable
def test_finding_immutable(mem):
    mem.save_finding(finding())
    with pytest.raises(ValueError, match="immutable"):
        mem.save_finding(finding())


def test_supersede_keeps_history(mem):
    old = finding()
    mem.save_finding(old)
    new = finding("fnd-ddd444", conf=0.9)
    mem.supersede_finding("fnd-ccc333", new)
    active = mem.active_findings()
    assert len(active) == 1
    assert active[0].finding_id == "fnd-ddd444"


def test_active_findings_filters_kinds(mem):
    mem.save_spec(spec())
    mem.save_finding(finding())
    mem.save_finding(finding("fnd-eee555", kind="refuted", conf=0.3))
    refuted = mem.active_findings(kinds=["refuted"])
    assert [f.finding_id for f in refuted] == ["fnd-eee555"]


# ---- champion + circuit breaker
def test_champion_roundtrip(mem):
    assert mem.get_champion() is None
    mem.set_champion({"lr": 0.01}, 0.021, "exp-aaa111")
    c = mem.get_champion()
    assert c["metric_value"] == 0.021


def test_consecutive_failures_streak(mem):
    for i, eid in enumerate(["exp-f01001", "exp-f01002", "exp-f01003"]):
        mem.save_spec(spec(eid))
        mem.save_result(ExperimentResult(
            experiment_id=eid, status="failed",
            error={"code": "crash", "message": "boom"}))
    assert mem.consecutive_failures() == 3
    mem.save_spec(spec("exp-ok0001"))
    mem.save_result(result("exp-ok0001", value=0.03))
    assert mem.consecutive_failures() == 0


def _failed(eid):
    return ExperimentResult(
        experiment_id=eid, status="failed",
        error={"code": "crash", "message": "boom"},
    )


def spec_trees(eid):
    return ExperimentSpec(
        experiment_id=eid, project_id="numerai-demo", hypothesis_id="hyp-bbb222",
        changes=[Change(parameter="n_trees", value=200)],
        reproducibility={"seed": 42},
    )


def test_three_similar_failures_halt_and_alert(mem):
    from kav_sdk.tools import make_kav_tools

    tools = {t.__name__: t for t in make_kav_tools(mem)}
    ids = ["exp-f02001", "exp-f02002", "exp-f02003"]
    for eid in ids:
        mem.save_spec(spec(eid))
        out = tools["ingest_result"](_failed(eid).model_dump_json())
    assert out.startswith("HALTED")
    assert mem.is_halted()
    assert mem.consecutive_similar_failures() == 3
    alerts = mem.active_findings(kinds=["operational"])
    assert len(alerts) == 1
    assert alerts[0].experiment_id == "exp-f02003"
    assert "circuit breaker" in alerts[0].statement.lower()
    assert "circuit-breaker" in alerts[0].tags


def test_dissimilar_failures_do_not_halt(mem):
    from kav_sdk.tools import make_kav_tools

    tools = {t.__name__: t for t in make_kav_tools(mem)}
    mem.save_spec(spec("exp-f03001"))
    mem.save_spec(spec("exp-f03002"))
    mem.save_spec(spec_trees("exp-f03003"))
    tools["ingest_result"](_failed("exp-f03001").model_dump_json())
    tools["ingest_result"](_failed("exp-f03002").model_dump_json())
    out = tools["ingest_result"](_failed("exp-f03003").model_dump_json())
    assert out.startswith("RECORDED")
    assert not mem.is_halted()
    assert mem.consecutive_failures() == 3
    assert mem.consecutive_similar_failures() == 1


def test_issue_spec_refused_until_resume(mem):
    from kav_sdk.tools import make_kav_tools

    mem.save_manifest(manifest())
    mem.save_search_space(space())
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    for eid in ["exp-f04001", "exp-f04002", "exp-f04003"]:
        mem.save_spec(spec(eid))
        tools["ingest_result"](_failed(eid).model_dump_json())
    blocked = tools["issue_spec"](spec("exp-f04004").model_dump_json())
    assert blocked.startswith("HALTED")
    assert tools["resume_strategy"]() == "RESUMED"
    assert not mem.is_halted()
    issued = tools["issue_spec"](spec("exp-f04004").model_dump_json())
    assert issued.startswith("ISSUED")


# ---- auto_guarded promotion (D-028)
def _confirmed(fid, eid, statement="Raising lr improved correlation."):
    return ResearchFinding(
        finding_id=fid, project_id="numerai-demo", experiment_id=eid,
        hypothesis_id="hyp-bbb222", kind="confirmed",
        statement=statement, confidence=0.7, tags=["lr"],
    )


def _harmful(fid, eid):
    return ResearchFinding(
        finding_id=fid, project_id="numerai-demo", experiment_id=eid,
        hypothesis_id="hyp-bbb222", kind="harmful",
        statement="This config used a forbidden validation-set peek.",
        confidence=0.8, tags=["forbidden"],
    )


def test_manual_default_does_not_auto_promote(mem):
    from kav_sdk.tools import make_kav_tools

    mem.save_manifest(manifest())
    mem.save_search_space(space())
    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    mem.save_spec(spec("exp-p01001", seed=1))
    mem.save_result(result("exp-p01001", value=0.030))
    mem.save_spec(spec("exp-p01002", seed=2))
    mem.save_result(result("exp-p01002", value=0.031))
    tools["record_finding"](_confirmed("fnd-p01001", "exp-p01001").model_dump_json())
    out = tools["record_finding"](_confirmed("fnd-p01002", "exp-p01002").model_dump_json())
    assert out.startswith("RECORDED")
    assert "PROMOTED" not in out
    assert mem.get_champion()["metric_value"] == 0.021


def test_auto_guarded_promotes_on_two_independent_confirmations(mem):
    from kav_sdk.memory import PROMOTION_AUTO_GUARDED
    from kav_sdk.tools import make_kav_tools

    mem.save_manifest(manifest())
    mem.save_search_space(space())
    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    mem.set_promotion_policy(PROMOTION_AUTO_GUARDED)
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    mem.save_spec(spec("exp-p02001", seed=11))
    mem.save_result(result("exp-p02001", value=0.028))
    first = tools["record_finding"](_confirmed("fnd-p02001", "exp-p02001").model_dump_json())
    assert first == "RECORDED fnd-p02001"
    assert mem.get_champion()["metric_value"] == 0.021
    mem.save_spec(spec("exp-p02002", seed=12))
    mem.save_result(result("exp-p02002", value=0.030))
    second = tools["record_finding"](_confirmed("fnd-p02002", "exp-p02002").model_dump_json())
    assert "PROMOTED" in second
    champ = mem.get_champion()
    assert champ["metric_value"] == 0.030
    assert champ["experiment_id"] == "exp-p02002"
    notices = mem.active_findings(kinds=["operational"])
    assert len(notices) == 1
    assert "auto-guarded" in notices[0].tags
    assert "auto-guarded promotion" in notices[0].statement.lower()
    policy = mem.get_promotion_policy()
    assert policy["mode"] == PROMOTION_AUTO_GUARDED


def test_auto_guarded_same_seed_is_not_independent(mem):
    from kav_sdk.memory import PROMOTION_AUTO_GUARDED
    from kav_sdk.tools import make_kav_tools

    mem.save_manifest(manifest())
    mem.save_search_space(space())
    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    mem.set_promotion_policy(PROMOTION_AUTO_GUARDED)
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    mem.save_spec(spec("exp-p03001", seed=7))
    mem.save_result(result("exp-p03001", value=0.028))
    mem.save_spec(spec("exp-p03002", seed=7))
    mem.save_result(result("exp-p03002", value=0.029))
    tools["record_finding"](_confirmed("fnd-p03001", "exp-p03001").model_dump_json())
    out = tools["record_finding"](_confirmed("fnd-p03002", "exp-p03002").model_dump_json())
    assert "PROMOTED" not in out
    assert mem.get_champion()["metric_value"] == 0.021


def test_auto_guarded_harmful_finding_blocks(mem):
    from kav_sdk.memory import PROMOTION_AUTO_GUARDED
    from kav_sdk.tools import make_kav_tools

    mem.save_manifest(manifest())
    mem.save_search_space(space())
    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    mem.set_promotion_policy(PROMOTION_AUTO_GUARDED)
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    mem.save_spec(spec("exp-p04001", seed=21))
    mem.save_result(result("exp-p04001", value=0.028))
    mem.save_spec(spec("exp-p04002", seed=22))
    mem.save_result(result("exp-p04002", value=0.030))
    tools["record_finding"](_confirmed("fnd-p04001", "exp-p04001").model_dump_json())
    tools["record_finding"](_harmful("fnd-p0400h", "exp-p04002").model_dump_json())
    out = tools["record_finding"](_confirmed("fnd-p04002", "exp-p04002").model_dump_json())
    assert "PROMOTED" not in out
    assert mem.get_champion()["metric_value"] == 0.021


def test_auto_guarded_below_threshold_does_not_promote(mem):
    from kav_sdk.memory import PROMOTION_AUTO_GUARDED
    from kav_sdk.tools import make_kav_tools

    mem.save_manifest(manifest())
    mem.save_search_space(space())
    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    mem.set_promotion_policy(PROMOTION_AUTO_GUARDED, min_delta=0.02)
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    mem.save_spec(spec("exp-p05001", seed=31))
    mem.save_result(result("exp-p05001", value=0.025))
    mem.save_spec(spec("exp-p05002", seed=32))
    mem.save_result(result("exp-p05002", value=0.026))
    tools["record_finding"](_confirmed("fnd-p05001", "exp-p05001").model_dump_json())
    out = tools["record_finding"](_confirmed("fnd-p05002", "exp-p05002").model_dump_json())
    assert "PROMOTED" not in out
    assert mem.get_champion()["metric_value"] == 0.021


def test_auto_guarded_minimize_direction(mem):
    from kav_sdk.memory import PROMOTION_AUTO_GUARDED
    from kav_sdk.tools import make_kav_tools

    m = ProjectManifest(
        project_id="numerai-demo", name="Demo",
        objective=Objective(metric="loss", direction="minimize"),
        constraints=Constraints(max_budget_per_experiment=Budget(max_compute_hours=2)),
        evaluator=EvaluatorDecl(owned_by="host"),
    )
    mem.save_manifest(m)
    mem.save_search_space(space())
    mem.set_champion({"lr": 0.01}, 0.40, "exp-baseline")
    mem.set_promotion_policy(PROMOTION_AUTO_GUARDED)
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    mem.save_spec(spec("exp-p06001", seed=41))
    mem.save_result(result("exp-p06001", value=0.35))
    mem.save_spec(spec("exp-p06002", seed=42))
    mem.save_result(result("exp-p06002", value=0.33))
    tools["record_finding"](_confirmed("fnd-p06001", "exp-p06001").model_dump_json())
    out = tools["record_finding"](_confirmed("fnd-p06002", "exp-p06002").model_dump_json())
    assert "PROMOTED" in out
    assert mem.get_champion()["metric_value"] == 0.33


def test_auto_guarded_halt_blocks_promotion(mem):
    from kav_sdk.memory import PROMOTION_AUTO_GUARDED
    from kav_sdk.tools import make_kav_tools

    mem.save_manifest(manifest())
    mem.save_search_space(space())
    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    mem.set_promotion_policy(PROMOTION_AUTO_GUARDED)
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    for eid in ["exp-p07001", "exp-p07002", "exp-p07003"]:
        mem.save_spec(spec(eid))
        tools["ingest_result"](_failed(eid).model_dump_json())
    assert mem.is_halted()
    mem.save_spec(spec("exp-p07004", seed=51))
    mem.save_result(result("exp-p07004", value=0.030))
    mem.save_spec(spec("exp-p07005", seed=52))
    mem.save_result(result("exp-p07005", value=0.031))
    tools["record_finding"](_confirmed("fnd-p07004", "exp-p07004").model_dump_json())
    out = tools["record_finding"](_confirmed("fnd-p07005", "exp-p07005").model_dump_json())
    assert "PROMOTED" not in out
    assert mem.get_champion()["metric_value"] == 0.021


def test_human_promote_still_works_in_auto_guarded(mem):
    from kav_sdk.memory import PROMOTION_AUTO_GUARDED
    from kav_sdk.tools import make_kav_tools

    mem.set_promotion_policy(PROMOTION_AUTO_GUARDED)
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    out = tools["promote"]({"lr": 0.02}, 0.024, "exp-human01")
    assert out.startswith("PROMOTED")
    assert mem.get_champion()["metric_value"] == 0.024


def test_save_manifest_without_policy_seeds_manual(mem):
    mem.save_manifest(manifest())
    assert mem.get_promotion_policy()["mode"] == PROMOTION_MANUAL


def test_save_manifest_auto_guarded_seeds_policy(mem):
    mem.save_manifest(manifest().model_copy(
        update={"policy": PolicyDecl(promotion="auto_guarded")}
    ))
    assert mem.get_promotion_policy()["mode"] == PROMOTION_AUTO_GUARDED


def test_save_manifest_preserves_local_thresholds(mem):
    mem.set_promotion_policy(PROMOTION_MANUAL, min_delta=0.01, confirmations=3)
    mem.save_manifest(manifest().model_copy(
        update={"policy": PolicyDecl(promotion="auto_guarded")}
    ))
    policy = mem.get_promotion_policy()
    assert policy["mode"] == PROMOTION_AUTO_GUARDED
    assert policy["min_delta"] == 0.01
    assert policy["confirmations"] == 3


def test_save_manifest_omitted_policy_reverts_to_manual(mem):
    mem.set_promotion_policy(PROMOTION_AUTO_GUARDED)
    mem.save_manifest(manifest())
    assert mem.get_promotion_policy()["mode"] == PROMOTION_MANUAL


def test_observe_includes_promotion_policy(mem):
    from kav_sdk.memory import PROMOTION_AUTO_GUARDED
    from kav_sdk.tools import make_kav_tools
    import json

    tools = {t.__name__: t for t in make_kav_tools(mem)}
    state = json.loads(tools["observe"]())
    assert state["promotion_policy"]["mode"] == "manual"
    mem.set_promotion_policy(PROMOTION_AUTO_GUARDED, min_delta=0.01, confirmations=3)
    state = json.loads(tools["observe"]())
    assert state["promotion_policy"] == {
        "mode": PROMOTION_AUTO_GUARDED,
        "min_delta": 0.01,
        "confirmations": 3,
    }


# ---- minimal desk + rejuvenation (D-029)
def test_desk_is_champion_plus_top_k(mem):
    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    mem.set_desk_policy(k=2)
    mem.save_spec(spec("exp-d01001"))
    mem.save_finding(finding("fnd-d01001", kind="confirmed", conf=0.9))
    mem.save_finding(finding("fnd-d01002", kind="confirmed", conf=0.4))
    mem.save_finding(finding("fnd-d01003", kind="inconclusive", conf=0.2))
    desk = mem.desk()
    assert desk["k"] == 2
    assert desk["mode"] == DESK_MINIMAL
    assert "digest" not in desk
    assert desk["champion"]["metric_value"] == 0.021
    assert [f["finding_id"] for f in desk["findings"]] == ["fnd-d01001", "fnd-d01002"]
    assert desk["rejuvenated"] == []


def test_desk_excludes_superseded_until_rejuvenation(mem):
    mem.save_spec(spec("exp-d02001"))
    mem.save_finding(finding("fnd-d02001", kind="refuted", conf=0.6))
    mem.supersede_finding("fnd-d02001", finding("fnd-d02002", kind="confirmed", conf=0.8))
    desk = mem.desk()
    assert [f["finding_id"] for f in desk["findings"]] == ["fnd-d02002"]
    discarded = mem.discarded_findings()
    assert [f.finding_id for f in discarded] == ["fnd-d02001"]


def test_plateau_rejuvenates_superseded_finding(mem):
    from kav_sdk.tools import make_kav_tools

    mem.save_manifest(manifest())
    mem.save_search_space(space())
    mem.set_champion({"lr": 0.01}, 0.050, "exp-baseline")
    mem.set_desk_policy(k=10, rejuvenation_every=99, plateau_window=3)
    mem.save_spec(spec("exp-d03000"))
    mem.save_finding(finding("fnd-d03000", kind="refuted", conf=0.55))
    mem.supersede_finding("fnd-d03000", finding("fnd-d0300n", kind="confirmed", conf=0.8))
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    for i, eid in enumerate(["exp-d03001", "exp-d03002", "exp-d03003"], start=1):
        mem.save_spec(spec(eid, seed=i))
        out = tools["ingest_result"](result(eid, value=0.040).model_dump_json())
    assert "REJUVENATED" in out
    desk = mem.desk()
    assert "fnd-d03000" in [f["finding_id"] for f in desk["rejuvenated"]]
    notices = [f for f in mem.active_findings(kinds=["operational"])
               if "rejuvenation" in f.tags]
    assert len(notices) == 1
    assert "plateau" in notices[0].tags


def test_periodic_rejuvenation_every_n_completed(mem):
    from kav_sdk.tools import make_kav_tools

    mem.save_manifest(manifest())
    mem.save_search_space(space())
    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    mem.set_desk_policy(k=10, rejuvenation_every=2, plateau_window=99)
    mem.save_spec(spec("exp-d04000"))
    mem.save_finding(finding("fnd-d04000", kind="refuted", conf=0.5))
    mem.supersede_finding("fnd-d04000", finding("fnd-d0400n", kind="confirmed", conf=0.9))
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    mem.save_spec(spec("exp-d04001", seed=1))
    first = tools["ingest_result"](result("exp-d04001", value=0.030).model_dump_json())
    assert "REJUVENATED" not in first
    mem.save_spec(spec("exp-d04002", seed=2))
    second = tools["ingest_result"](result("exp-d04002", value=0.031).model_dump_json())
    assert "REJUVENATED" in second
    notices = [f for f in mem.active_findings(kinds=["operational"])
               if "periodic" in f.tags]
    assert len(notices) == 1


def test_new_search_space_parameter_rejuvenates(mem):
    from kav_sdk.tools import make_kav_tools

    mem.save_manifest(manifest())
    mem.save_search_space(space())
    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    mem.set_desk_policy(k=10, rejuvenation_every=99, plateau_window=99)
    old = ResearchFinding(
        finding_id="fnd-d05000", project_id="numerai-demo", experiment_id="exp-aaa111",
        kind="refuted", statement="lr=0.09 hurt correlation on the old feature set.",
        confidence=0.6, tags=["lr"],
        conditions={"config_snapshot": {"lr": 0.09}},
    )
    mem.save_spec(spec("exp-d05000"))
    mem.save_finding(old)
    mem.supersede_finding("fnd-d05000", finding("fnd-d0500n", kind="confirmed", conf=0.9))
    mem.save_search_space(SearchSpace(
        project_id="numerai-demo",
        parameters=[
            Parameter(name="lr", type="number", domain=Domain(kind="range", min=0.001, max=0.1)),
            Parameter(name="n_trees", type="integer", domain=Domain(kind="range", min=10, max=400)),
        ],
        defaults={"lr": 0.01, "n_trees": 100},
    ))
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    mem.save_spec(spec("exp-d05001", seed=3))
    out = tools["ingest_result"](result("exp-d05001", value=0.022).model_dump_json())
    assert "REJUVENATED" in out
    notices = [f for f in mem.active_findings(kinds=["operational"])
               if "conditions_changed" in f.tags]
    assert len(notices) == 1


def test_no_discarded_findings_skips_rejuvenation(mem):
    from kav_sdk.tools import make_kav_tools

    mem.save_manifest(manifest())
    mem.save_search_space(space())
    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    mem.set_desk_policy(k=10, rejuvenation_every=1, plateau_window=1)
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    mem.save_spec(spec("exp-d06001"))
    out = tools["ingest_result"](result("exp-d06001", value=0.022).model_dump_json())
    assert "REJUVENATED" not in out
    assert tools["rejuvenate"]() == "NO_CANDIDATES"


def test_human_rejuvenate_forces_desk_slot(mem):
    from kav_sdk.tools import make_kav_tools

    mem.save_manifest(manifest())
    mem.save_search_space(space())
    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    mem.set_desk_policy(k=10, rejuvenation_every=99, plateau_window=99)
    mem.save_spec(spec("exp-d07000"))
    mem.save_result(result("exp-d07000", value=0.022))
    mem.save_finding(finding("fnd-d07000", kind="refuted", conf=0.4))
    mem.supersede_finding("fnd-d07000", finding("fnd-d0700n", kind="confirmed", conf=0.9))
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    assert tools["rejuvenate"]() == "REJUVENATED"
    desk = mem.desk()
    assert "fnd-d07000" in [f["finding_id"] for f in desk["rejuvenated"]]
    notices = [f for f in mem.active_findings(kinds=["operational"]) if "manual" in f.tags]
    assert len(notices) == 1


def test_observe_includes_desk(mem):
    from kav_sdk.tools import make_kav_tools
    import json

    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    state = json.loads(tools["observe"]())
    assert state["desk"]["k"] == 10
    assert state["desk"]["mode"] == DESK_MINIMAL
    assert "digest" not in state["desk"]
    assert state["desk"]["champion"]["metric_value"] == 0.021
    assert state["desk"]["findings"] == state["active_findings"]
    assert state["desk_policy"]["k"] == 10
    assert state["desk_policy"]["mode"] == DESK_MINIMAL
    assert state["execution_policy"]["max_inflight"] == 2
    assert state["pending"] == []
    assert state["inflight"] == []
    assert state["wakes"] == []


# ---- event-driven wake / in-flight (D-030)
def test_mark_started_moves_spec_from_pending_to_inflight(mem):
    mem.save_spec(spec("exp-wake01"))
    mem.save_spec(spec("exp-wake02"))
    assert [s.experiment_id for s in mem.pending_specs()] == ["exp-wake01", "exp-wake02"]
    mem.mark_started("exp-wake01")
    assert [s.experiment_id for s in mem.pending_specs()] == ["exp-wake02"]
    assert [s.experiment_id for s in mem.inflight_specs()] == ["exp-wake01"]
    mem.save_result(result("exp-wake01"))
    assert mem.inflight_specs() == []
    assert [w["experiment_id"] for w in mem.unconsumed_wakes()] == ["exp-wake01"]
    assert [w["kind"] for w in mem.unconsumed_wakes()] == ["result_ingested"]


def test_observe_consumes_wakes_once(mem):
    from kav_sdk.tools import make_kav_tools
    import json

    mem.save_spec(spec("exp-wake10"))
    mem.save_result(result("exp-wake10"))
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    first = json.loads(tools["observe"]())
    assert [w["experiment_id"] for w in first["wakes"]] == ["exp-wake10"]
    second = json.loads(tools["observe"]())
    assert second["wakes"] == []


def test_execution_policy_rejects_non_positive_inflight(mem):
    with pytest.raises(ValueError, match="max_inflight"):
        mem.set_execution_policy(max_inflight=0)


# ---- rich-history digest as desk config (D-031)
def test_rich_digest_is_a_desk_config_change(mem):
    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    mem.set_desk_policy(k=1, mode=DESK_RICH_DIGEST)
    mem.save_spec(spec("exp-d08001"))
    mem.save_finding(finding("fnd-d08001", kind="confirmed", conf=0.9))
    mem.save_finding(finding("fnd-d08002", kind="inconclusive", conf=0.3))
    mem.supersede_finding("fnd-d08002", finding("fnd-d08003", kind="refuted", conf=0.4))
    desk = mem.desk()
    assert desk["mode"] == DESK_RICH_DIGEST
    assert [f["finding_id"] for f in desk["findings"]] == ["fnd-d08001"]
    digest = desk["digest"]
    assert digest["total_findings"] == 3
    assert digest["superseded"] == 1
    assert digest["by_kind"]["confirmed"] == 1
    off_ids = {item["finding_id"] for item in digest["off_desk"]}
    assert "fnd-d08001" not in off_ids
    assert "fnd-d08002" in off_ids
    assert "fnd-d08003" in off_ids
    superseded_row = next(item for item in digest["off_desk"] if item["finding_id"] == "fnd-d08002")
    assert superseded_row["superseded"] is True
    assert digest["off_desk_truncated"] == 0


def test_desk_mode_switch_drops_digest(mem):
    mem.set_desk_policy(k=10, mode=DESK_RICH_DIGEST)
    assert "digest" in mem.desk()
    mem.set_desk_policy(k=10, mode=DESK_MINIMAL)
    assert mem.desk()["mode"] == DESK_MINIMAL
    assert "digest" not in mem.desk()


def test_set_desk_policy_preserves_mode_when_omitted(mem):
    mem.set_desk_policy(k=4, mode=DESK_RICH_DIGEST)
    mem.set_desk_policy(k=2)
    policy = mem.get_desk_policy()
    assert policy["k"] == 2
    assert policy["mode"] == DESK_RICH_DIGEST


def test_unknown_desk_mode_rejected(mem):
    with pytest.raises(ValueError, match="unknown desk mode"):
        mem.set_desk_policy(mode="verbose")


def test_observe_rich_digest_includes_digest(mem):
    from kav_sdk.tools import make_kav_tools
    import json

    mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")
    mem.set_desk_policy(k=10, mode=DESK_RICH_DIGEST)
    mem.save_spec(spec("exp-d09001"))
    mem.save_finding(finding("fnd-d09001", kind="confirmed", conf=0.8))
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    state = json.loads(tools["observe"]())
    assert state["desk_policy"]["mode"] == DESK_RICH_DIGEST
    assert state["desk"]["digest"]["total_findings"] == 1
    assert state["desk"]["digest"]["off_desk"] == []
