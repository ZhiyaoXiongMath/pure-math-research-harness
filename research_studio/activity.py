"""Read-only activity navigation derived from native visits and requests.

This projection is not a scheduler, stage-completion ledger or proof verdict.
"""
from .util import require
from .workflows.registry import definition, ROUTES


def stage_order(stage_id):
    return -1 if stage_id.startswith("MAIN_") else int(stage_id[1:])


def graph():
    registry = definition()
    workflows = []
    for kind in ('TRH', 'FDH', 'SURVEY'):
        rows = [s for s in registry['stages'].values() if s['workflow_kind'] == kind]
        rows.sort(key=lambda s: stage_order(s['stage_id']))
        nodes, edges = [], []
        for row in rows:
            stage = row['stage_id']
            nodes.append({'stage_id': stage, 'label': row['ui_labels']['zh-CN'],
                          'purpose': row['purpose'], 'roles': [r['role'] for r in row['roles']]})
            for edge_kind in ('forward', 'return'):
                edges.extend({'from': stage, 'to': target, 'kind': edge_kind}
                             for target in row['exit_rules'][edge_kind])
            if row['exit_rules'].get('early_delivery'):
                edges.append({'from': stage, 'to': row['exit_rules']['early_delivery'], 'kind': 'early_delivery'})
        workflows.append({'kind': kind, 'nodes': nodes, 'edges': edges})
    return {'registry_digest': registry['digest'], 'workflows': workflows,
            'analysis_routes': [{'id': route, 'roles': list(roles), 'label': label}
                                for (route, roles), label in zip(ROUTES.items(),
                                    ('来源应用：学习与适用性', '直接分析', '比较路线：学习、直接分析，再综合'))],
            'handoffs': [{'from': 'TRH', 'to': 'FDH', 'to_stage': 'D0',
                          'label': '从当前固定目标开展表述发现', 'human_decision_required': True},
                         {'from': 'FDH', 'to': 'TRH', 'to_stage': 'P0',
                          'label': '采用精确候选，建立暂停的定题研究', 'human_decision_required': True},
                         {'from':'SURVEY','to':'TRH','to_stage':'P0','label':'采用调查中的精确命题，建立暂停的定题研究','human_decision_required':True},
                         {'from':'SURVEY','to':'FDH','to_stage':'D0','label':'从调查中的问题建立暂停的表述发现','human_decision_required':True}],
            'navigation_only': True, 'automatic_next': False, 'completion_is_not_proof': True}


def _instance(snapshot, iid):
    instance = snapshot['instances'][iid]
    registry = definition()['stages']
    stages = {sid: {'stage_id': sid, 'label': row['ui_labels']['zh-CN'],
                    'status': 'UNVISITED', 'task_ids': [], 'request_ids': [],
                    'visit_ids': [], 'control_event_ids': [], 'record_refs': [], 'waiting_reasons': [], 'next_actions': []}
              for sid, row in registry.items() if row['workflow_kind'] == instance['kind']}
    # These native arrays retain chronological visit order even when the
    # canonical snapshot serializes dictionaries in lexicographic key order.
    recent = []
    # Human setup/selection is native work too, but it does not imply an
    # in-flight request or a mathematically completed stage. Control scope
    # versions and stage visits have different clocks, so do not interleave
    # their IDs to manufacture a most-recent research stage.
    for event in snapshot.get('control_events', {}).values():
        kind = event['event_type']; payload = event.get('payload', {})
        owner = event.get('instance_id') or payload.get('instance', {}).get('instance_id')
        if owner != iid:
            continue
        stage_id = None
        if kind in {'CREATE_INSTANCE', 'DISCOVERY_SCOPE_DEFINED'} or (kind == 'AUTHORIZE_MISSION' and 'mission' in payload):
            stage_id = {'TRH':'P0','FDH':'D0','SURVEY':'S0'}[instance['kind']]
        elif kind in {'HUMAN_DECISION', 'HANDOFF_PREPARED', 'HANDOFF_ADOPTED'} and instance['kind']!='TRH':
            stage_id = {'TRH':'P14','FDH':'D5','SURVEY':'S7'}[instance['kind']]
        elif kind == 'REPORT_SELECTED':
            stage_id = {'TRH':'P13','FDH':'D5','SURVEY':'S6'}[instance['kind']]
        if stage_id:
            stages[stage_id]['status'] = 'VISITED'
            stages[stage_id]['control_event_ids'].append(event['event_id'])
    for mid in instance.get('mission_ids', []):
        mission = snapshot.get('missions', {}).get(mid, {})
        for vid in mission.get('stage_visit_ids', []):
            visit = snapshot.get('visits', {}).get(vid)
            if not visit or visit.get('instance_id') != iid or visit['stage_id'] not in stages:
                continue
            stage = stages[visit['stage_id']]
            stage['visit_ids'].append(vid)
            stage['status'] = 'VISITED'
            recent = [visit['stage_id']]
    # Host progress/fault accounting is not a visited P13 scientific task.
    tasks = {tid: t for tid, t in snapshot.get('tasks', {}).items() if t['instance_id'] == iid}
    running, waiting = set(), set()
    if instance['kind']=='TRH':
        # A technical pause/continue or handoff is a real control event, but
        # cannot stand in for arrival at the scientific P13/P14 boundary.
        p14=stages['P14']
        p14['delivery_ids']=[did for did,row in snapshot.get('round_deliveries',{}).items()
            if row.get('instance_id')==iid and (row.get('delivery_kind') or row.get('summary',{}).get('delivery_kind'))=='P13_P14']
        decisions=[row['event_id'] for row in snapshot.get('main_decisions',{}).values()
            if row.get('instance_id')==iid and row.get('event_type')=='MAIN_P14_DECISION']
        p14['control_event_ids'].extend(decisions)
        human_wait=instance.get('run_control',{}).get('state')=='WAITING_HUMAN_AT_P14'
        if p14['delivery_ids'] or decisions or human_wait:p14['status']='VISITED'
        if human_wait:
            waiting.add('P14');p14['waiting_reasons'].append('WAITING_HUMAN_AT_P14')
    for tid, task in tasks.items():
        if task['stage_id'] not in stages:
            continue
        stage = stages[task['stage_id']]
        stage['task_ids'].append(tid)
        request = snapshot.get('requests', {}).get(task['request_id'], {})
        stage['request_ids'].append(task['request_id'])
        if stage['status'] == 'UNVISITED':
            stage['status'] = 'VISITED'
        state = request.get('execution_state')
        if state in {'RESERVED', 'SENT'}:
            running.add(task['stage_id'])
        elif state == 'UNKNOWN' and request.get('unknown_disposition') == 'ABANDON_UNKNOWN':
            stage['waiting_reasons'].append('已放弃等待；发送结果与成本仍未知，保留预算占用，禁止重发原请求')
            stage['next_actions'].append('查看保留的原请求及人工处置记录')
        elif state in {'PREPARED', 'CAPTURED', 'UNKNOWN'}:
            waiting.add(task['stage_id'])
            reason = {'PREPARED': '等待发送已有冻结请求', 'CAPTURED': '已有捕获等待接纳',
                      'UNKNOWN': '发送结果未知，等待人工处置'}[state]
            if request.get('fenced') or instance['status'] != 'ACTIVE':
                reason += '；实例已暂停或请求已隔离'
            stage['waiting_reasons'].append(reason)
            action = {'PREPARED': '检查任务与授权后继续', 'CAPTURED': '检查原始捕获并接纳',
                      'UNKNOWN': '查看并处置不确定请求'}[state]
            stage['next_actions'].append(action)
        if task.get('entry_basis', {}).get('analysis_route'):
            stage.setdefault('analysis_routes', []).append(task['entry_basis']['analysis_route'])
    for event in snapshot.get('production_events', {}).values():
        task = tasks.get(event.get('task_id'))
        if task and task['stage_id'] in stages and event.get('record_ref'):
            stages[task['stage_id']]['record_refs'].append(event['record_ref'])
    if instance['kind']=='SURVEY':
        from .survey import _ACTIVE_RETRIEVALS
        for item in snapshot.get('survey_events',{}).values():
            if item['instance_id']!=iid:continue
            sid='S5' if item['event_type'] in {'SNAPSHOT_FROZEN','OUTPUT_PLANNED'} else 'S1' if item['event_type'].startswith('RETRIEVAL_') else None
            if sid:
                stages[sid]['status']='VISITED';stages[sid]['control_event_ids'].append(item['event_id'])
        for retrieval in snapshot.get('survey_retrievals',{}).values():
            if retrieval['instance_id']!=iid or retrieval['status']!='RUNNING':continue
            if retrieval['id'] in _ACTIVE_RETRIEVALS:running.add('S1')
            else:
                waiting.add('S1');stages['S1']['waiting_reasons'].append('SURVEY_RETRIEVAL_UNKNOWN')
                stages['S1']['next_actions'].append('INSPECT_ORIGINAL_RETRIEVAL')
    for sid, stage in stages.items():
        if sid in running:
            stage['status'] = 'RUNNING'
        elif sid in waiting:
            stage['status'] = 'WAITING'
        for key in ('task_ids', 'request_ids', 'visit_ids', 'record_refs', 'waiting_reasons', 'next_actions', 'analysis_routes'):
            if key in stage:
                stage[key] = list(dict.fromkeys(stage[key]))
    order = stage_order
    return {'instance_id': iid, 'workflow_kind': instance['kind'], 'name': instance.get('name'),
            'instance_status': instance['status'], 'active_stages': sorted(running, key=order),
            'waiting_stages': sorted(waiting - running, key=order), 'recent_stages': recent,
            'recent_basis': 'NATIVE_MISSION_VISIT_ORDER',
            'summary': '当前有在途请求' if running else '当前无在途活动',
            'stages': sorted(stages.values(), key=lambda s: order(s['stage_id'])),
            'completion_is_not_proof': True}


def project(snapshot, instance_id=None):
    require(instance_id is None or instance_id in snapshot['instances'], 'INSTANCE_UNKNOWN', '请选择已有研究流程。')
    instances = [_instance(snapshot, iid) for iid in snapshot['instances']]
    if instance_id:
        selected = next(row for row in instances if row['instance_id'] == instance_id)
        return {**selected, 'instances': [{k: v for k, v in row.items() if k != 'stages'} for row in instances]}
    return {'instance_id': None, 'workflow_kind': None, 'instance_status': None,
            'active_stages': [], 'waiting_stages': [], 'recent_stages': [], 'stages': [],
            'summary': '项目总览：请选择一个研究流程查看其活动', 'instances': instances,
            'completion_is_not_proof': True}
