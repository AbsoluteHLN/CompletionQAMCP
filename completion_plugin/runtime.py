"""Approved local review execution integrated with task state and usage."""
from .evidence import Review


def execute_review(workflow, task, *, root, artifacts, ledger, trusted_tests=False):
    if type(trusted_tests) is not bool: raise ValueError('trusted_tests must be a boolean')
    from pathlib import Path
    inputs=workflow.data['tasks'][task].get('inputs')
    if inputs and inputs != {'root':str(Path(root).resolve()),'artifacts':list(artifacts)}: raise ValueError('Execution inputs differ from approved task')
    mode=workflow.data['tasks'][task].get('code_mode')
    if (mode=='project_tests') != (trusted_tests is True): raise ValueError('Execution checker differs from approved code mode')
    workflow.start(task)  # before any execution
    try:
        review = Review(root, artifacts, workflow.data['revision'])
        if trusted_tests is True: review.project_tests(explicitly_trusted=True)
        else: review.syntax()
        required = list(workflow.data['tasks'][task]['required_checks'])
        workflow._verifiers[task] = lambda: review.gate(required)['allow_completion'] is True
        result = review.gate(required)
        status = 'pass' if result['allow_completion'] else 'fail'
    except Exception as exc:
        status, result = 'blocked', {'reason':type(exc).__name__}
    attempt = ledger.record(task=task,model='local-no-model',status=status,provider='local',
                            operation='project_tests' if trusted_tests is True else 'syntax_check')
    workflow.finish(task,status=status,result={'review':result,'usage':attempt})
    return {'status':status,'review':result,'usage':attempt}


def dispatch_profile(workflow, task, *, profile, validator, context, ledger, supervisor,
                     host_concurrency, execute=None, budget=None):
    """Route an approved task through a trusted host, leaving final QA explicit."""
    from .profiles import ProfileError
    declaration = workflow.data['tasks'][task]
    binding = declaration.get('profile_binding') or {}
    approval = workflow.data.get('approval')
    if approval != workflow._proposal() or binding.get('profile_id') != profile.profile_id or binding.get('revision') != profile.profile_revision:
        raise ValueError('Task/profile approval is missing or stale')
    if execute is None:
        return {'status':'blocked','reason':'Host execution unavailable','usage':'unknown'}
    if budget and not ledger.budget_allows(budget['ceiling'],budget['currency'],next_max_cost=budget.get('enforced_next_max_cost')):
        return {'status':'blocked','reason':'Hard budget cannot be guaranteed'}
    role = binding.get('role')
    approved_routes = binding.get('approved_routes',[])
    # Recheck only approved routes through the configured validator; authorization
    # for any actual smoke belongs to that trusted validator, not model arguments.
    for route_id in approved_routes:
        validator.validate(profile,route_id,'recheck',context)
    try:
        route, concurrency, reasons = validator.select_route(profile,role,context,
            approved_revision=binding['revision'],approved_routes=approved_routes,
            host_concurrency=host_concurrency)
    except ProfileError as exc:
        supervisor.observe(task,kind='blocker',detail=str(exc))
        return {'status':'blocked','reason':str(exc)}
    workflow.start(task)
    try:
        response=execute(route,concurrency,declaration['acceptance'])
        if not isinstance(response,dict): raise ValueError('Invalid host response')
        usage=response.get('usage') or {}
        measured=usage.get('source','unknown')
        entry=ledger.record(task=task,model=route.model,provider=route.provider,status='pass',
            operation='host_generation',tokens=usage.get('tokens'),
            cost=usage.get('cost'),currency=usage.get('currency'),measurement_source=measured)
        # Host generation success is not task QA success.
        workflow.finish(task,status='blocked',result={'reason':'Output requires declared acceptance QA','usage':entry,'output':response.get('output')})
        supervisor.observe(task,kind='artifact',detail='Host output received; acceptance QA pending')
        return {'status':'review_required','route':route.route_id,'output':response.get('output'),'usage':entry,'skipped':reasons}
    except Exception as exc:
        entry=ledger.record(task=task,model=route.model,provider=route.provider,status='fail',
                            operation='host_generation')
        workflow.finish(task,status='blocked',result={'reason':type(exc).__name__,'usage':entry})
        supervisor.observe(task,kind='blocker',detail=type(exc).__name__)
        return {'status':'blocked','reason':type(exc).__name__,'usage':entry}
