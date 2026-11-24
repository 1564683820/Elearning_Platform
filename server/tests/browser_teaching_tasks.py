"""Browser UI contract regression using explicitly synthetic HTTP fixtures.

Run separately with a Vite server on 127.0.0.1:5173. This is not live integration.
Requires optional `pip install playwright` and installed Microsoft Edge.
"""
import copy
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    output = Path(__file__).resolve().parents[1] / 'output' / 'teaching-browser'
    output.mkdir(parents=True, exist_ok=True)
    task_id = '9007199254740993'
    task = {'id': task_id, 'class_id': '80001', 'objective': '合成测试：过去时复习',
        'status': 'created', 'created_at': '2026-11-15T10:00:00', 'artifact': {},
        'artifact_version': 0, 'approved_version': None, 'published_exam_id': None, 'error_code': None,
        'checkpoint': {'config': {'question_count': 2, 'duration_minutes': 20}}}
    artifact = {'title': '过去时定向巩固', 'total_score': 10,
        'lesson': [{'title': '时间线与练习', 'minutes': 20, 'activity': '用昨日活动理解过去时。'}],
        'questions': [{'type': 'choice', 'stem': f'Yesterday, student {i} __ to school.',
            'options': ['went', 'go', 'goes', 'going'], 'answer': 'A', 'score': 5,
            'explanation': 'yesterday 表示过去时间。', 'knowledge_point': '一般过去时', 'citation_ids': ['C1']}
            for i in range(2)]}
    calls, errors = [], []

    def route_request(route):
        path, method = route.request.url.split('/api/v1')[-1], route.request.method
        calls.append((method, path))
        if path == '/teacher/classes':
            data = [{'id': '80001', 'name': '合成演示班级'}]
        elif path == '/teaching-tasks':
            data = task if method == 'POST' else [task]
        elif path.endswith('/run'):
            task['status'] = 'queued'
            data = task
        elif path.endswith('/events'):
            task.update(status='awaiting_review', artifact=copy.deepcopy(artifact), artifact_version=1)
            task['checkpoint'].update(completed=['analyze', 'retrieve', 'plan', 'generate', 'validate', 'await_review'],
                analysis={'exam_ids': ['40', '41'], 'submission_count': 4,
                    'topics': [{'knowledge_point': '一般过去时', 'wrong': 8, 'observations': 12}]},
                citations=[{'id': 'C1', 'document_id': '90001', 'title': '自编复习材料', 'page': 1,
                    'version': 'synthetic-version', 'snippet': '一般过去时描述过去发生的动作。'}])
            route.fulfill(status=200, content_type='text/event-stream', body='event: task\ndata: '+json.dumps(task)+'\n\n')
            return
        elif path.endswith('/artifact'):
            body = route.request.post_data_json
            assert body['version'] == task['artifact_version']
            task.update(artifact=body['artifact'], artifact_version=task['artifact_version']+1, status='awaiting_review', approved_version=None)
            data = task
        elif path.endswith('/approve'):
            assert route.request.post_data_json['version'] == task['artifact_version']
            task.update(status='approved', approved_version=task['artifact_version'])
            data = task
        elif path.endswith('/publish'):
            assert task['approved_version'] == task['artifact_version']
            task.update(status='published', published_exam_id='9007199254740995')
            data = task
        elif path.startswith('/teaching-tasks/'):
            data = task
        else:
            data = []
        route.fulfill(status=200, content_type='application/json', body=json.dumps({'code': 0, 'data': data}))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script("localStorage.setItem('token','synthetic-ui-test');localStorage.setItem('user',JSON.stringify({role:'teacher',nickname:'合成测试教师'}));")
        page.route('**/api/v1/**', route_request)
        page.goto('http://127.0.0.1:5173/Elearning/teaching-tasks')
        page.wait_for_load_state('networkidle')
        print('Rendered controls:', page.get_by_role('button').all_text_contents())
        page.get_by_label('目标班级').select_option('80001')
        page.get_by_label('练习题数').fill('2')
        page.get_by_role('button', name='创建任务', exact=True).click()
        page.get_by_role('button', name='开始备课', exact=True).click()
        expect(page.get_by_role('button', name='审核通过', exact=True)).to_be_visible()
        page.screenshot(path=str(output / 'review.png'), full_page=True)
        title = page.get_by_label('练习名称')
        title.fill('教师修订：过去时巩固')
        expect(page.get_by_role('button', name='审核通过', exact=True)).to_be_disabled()
        page.get_by_role('button', name='保存修改', exact=True).click()
        expect(page.get_by_text('版本 2', exact=False)).to_be_visible()
        page.get_by_role('button', name='审核通过', exact=True).click()
        page.get_by_role('button', name='发布到本班级', exact=True).click()
        expect(page.get_by_role('link', name='已发布，查看试卷')).to_be_visible()
        page.reload()
        page.wait_for_load_state('networkidle')
        page.get_by_role('button', name='合成测试：过去时复习').click()
        expect(page.get_by_role('link', name='已发布，查看试卷')).to_be_visible()
        page.set_viewport_size({'width': 768, 'height': 1024})
        page.screenshot(path=str(output / 'published-tablet.png'), full_page=True)
        assert not errors, errors
        assert any(path.endswith('/events') for _, path in calls)
        browser.close()
    print('PASS: synthetic UI review, SSE, dirty approval guard, save/version, publish, reload, tablet; no page errors')


if __name__ == '__main__':
    main()
