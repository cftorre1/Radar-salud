from scripts.orchestrator_liveness import evaluate, executable_tasks

def test_executable_tasks_require_satisfied_dependencies_and_no_blocker():
    queue={"tasks":[
        {"id":"done","status":"validated"},
        {"id":"ready","status":"approved","depends_on":["done"],"blocked_by":[]},
        {"id":"blocked","status":"in_progress","depends_on":["done"],"blocked_by":["human"]},
        {"id":"waiting","status":"approved","depends_on":["missing"],"blocked_by":[]},
    ]}
    assert executable_tasks(queue)==["ready"]

def test_liveness_marks_stalled_only_when_executable_work_is_old():
    queue={"tasks":[{"id":"ready","status":"in_progress","depends_on":[],"blocked_by":[]}]}
    assert evaluate(queue,20,75)["stalled"] is False
    result=evaluate(queue,90,75)
    assert result["stalled"] is True
    assert result["executable_tasks"]==["ready"]
