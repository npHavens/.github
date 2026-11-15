"""Runs the shell steps of the Claude review workflow against a stubbed gh."""

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unittest


root = Path(__file__).resolve().parents[1]
workflow = root / '.github' / 'workflows' / 'claude-review-reusable.yml'
caller = root / '.github' / 'workflows' / 'claude-review.yml'
comment_tool = 'mcp__github_inline_comment__create_inline_comment'
# The final record entry of a session that did, or never did, call the model.
used_result = {'type': 'result', 'modelUsage': {'some-model': {'outputTokens': 1}}}
unused_result = {'type': 'result', 'modelUsage': {}}

# Runs the real --jq filter on FAKE_API_JSON, so the summary's filter is tested too.
fake_gh = r'''#!/bin/bash
case "$1 $2" in
  "pr view")
    if [[ "$*" == *headRefOid* ]]; then [[ -z "$FAKE_HEAD_FAILS" ]] || exit 1; echo "$FAKE_HEAD"; exit 0; fi
    [[ -z "$FAKE_VIEW_FAILS" ]] || exit 1
    echo "$FAKE_CROSS_REPO" ;;
  "pr comment") printf '%s\n' "$5" >> "$FAKE_POSTED" ;;
  api*)
    [[ -z "$FAKE_API_FAILS" ]] || exit 1
    jq -r "$5" "$FAKE_API_JSON" ;;
esac
'''


def step_script(name):
    lines = workflow.read_text(encoding='utf-8').splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == f'- name: {name}')
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == 'run: |')
    indent = len(lines[run + 1]) - len(lines[run + 1].lstrip())
    body = []
    for line in lines[run + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        body.append(line[indent:])
    return '\n'.join(body) + '\n'


class ScriptCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        bin_dir = self.dir / 'bin'
        bin_dir.mkdir()
        gh = bin_dir / 'gh'
        gh.write_text(fake_gh, encoding='utf-8')
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.posted = self.dir / 'posted'
        self.posted.touch()
        self.env = dict(os.environ, PATH=f'{bin_dir}{os.pathsep}{os.environ["PATH"]}',
                        FAKE_POSTED=str(self.posted), GH_REPO='x/y', PR_NUMBER='1')

    def run_step(self, name, cwd=None, **env):
        return subprocess.run(['bash', '--noprofile', '--norc', '-e', '-o', 'pipefail', '-c', step_script(name)],
                              cwd=cwd or self.dir, env={**self.env, **env}, capture_output=True, text=True)

    def posts(self):
        return self.posted.read_text(encoding='utf-8').splitlines()


class GateTests(ScriptCase):
    def gate(self, event='issue_comment', body='', cross_repo='false', **env):
        output = self.dir / 'output'
        output.write_text('', encoding='utf-8')
        result = self.run_step('Decide whether to review', GITHUB_OUTPUT=str(output), GITHUB_EVENT_NAME=event,
                               COMMENT_BODY=body, FAKE_CROSS_REPO=cross_repo, **env)
        return result, 'proceed=true' in output.read_text(encoding='utf-8')

    def test_comment_must_start_with_the_exact_request(self):
        accepted = ('@claude review', '  @claude review', '@Claude Review', '@claude review please', '@claude review\nthanks')
        rejected = ('please @claude review', '@claude reviewer', '@claude review.', '@claude  review', '')
        for body in accepted:
            self.assertTrue(self.gate(body=body)[1], body)
        for body in rejected:
            self.assertFalse(self.gate(body=body)[1], body)
        self.assertEqual(self.posts(), [])

    def test_pull_request_event_proceeds_without_a_comment_or_lookup(self):
        result, proceed = self.gate(event='pull_request', FAKE_VIEW_FAILS='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(proceed)

    def test_fork_request_is_refused_out_loud(self):
        result, proceed = self.gate(body='@claude review', cross_repo='true')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(proceed)
        self.assertEqual(self.posts(), ['Claude review does not run on fork PRs.'])

    def test_lookup_failure_stops_the_review(self):
        result, proceed = self.gate(body='@claude review', FAKE_VIEW_FAILS='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(proceed)


class RestoreTests(ScriptCase):
    def tree(self, files, base):
        tree = self.dir / 'tree'
        for prefix, entries in ((tree, files), (tree / '.review-base', base)):
            for path, text in entries.items():
                target = prefix / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding='utf-8')
        return tree

    def restore(self, tree):
        result = self.run_step('Restore review rules from the default branch', cwd=tree)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rules_come_from_the_default_branch_at_any_depth(self):
        names = ('AGENTS.md', 'CODE_REVIEW.md', 'CLAUDE.md', 'CLAUDE.local.md')
        tree = self.tree({**{name: 'pr' for name in names}, **{f'sub/{name}': 'pr' for name in names}, 'keep.md': 'pr'},
                         {**{name: 'base' for name in names}, **{f'sub/{name}': 'base' for name in names}})
        self.restore(tree)
        for name in names:
            self.assertEqual((tree / name).read_text(encoding='utf-8'), 'base')
            self.assertEqual((tree / 'sub' / name).read_text(encoding='utf-8'), 'base')
        self.assertEqual((tree / 'keep.md').read_text(encoding='utf-8'), 'pr')
        self.assertFalse((tree / '.review-base').exists())

    def test_rules_the_pr_added_are_removed(self):
        tree = self.tree({f'added/{name}': 'pr' for name in ('AGENTS.md', 'CODE_REVIEW.md', 'CLAUDE.md', 'CLAUDE.local.md')},
                         {'AGENTS.md': 'base'})
        self.restore(tree)
        self.assertEqual(list((tree / 'added').iterdir()), [])

    def test_folder_replaced_by_a_file_does_not_stop_the_review(self):
        tree = self.tree({'foo': 'pr file'}, {'foo/AGENTS.md': 'base', 'AGENTS.md': 'base'})
        self.restore(tree)
        self.assertEqual((tree / 'foo').read_text(encoding='utf-8'), 'pr file')
        self.assertEqual((tree / 'AGENTS.md').read_text(encoding='utf-8'), 'base')


class SharedStandardTests(ScriptCase):
    def give(self, standard):
        case = Path(tempfile.mkdtemp(dir=self.dir))
        tree = case / 'tree'
        shared = tree / '.review-shared' / 'review'
        shared.mkdir(parents=True)
        if standard is not None:
            (shared / 'review-standard.md').write_text(standard, encoding='utf-8')
        home = case / 'home'
        (home / '.claude').mkdir(parents=True)
        (home / '.claude' / 'CLAUDE.md').write_text('existing rule\n', encoding='utf-8')
        result = self.run_step('Give the reviewer the shared review standard', cwd=tree, HOME=str(home))
        return result, tree, (home / '.claude' / 'CLAUDE.md').read_text(encoding='utf-8')

    def test_standard_is_appended_to_the_user_instructions_and_the_checkout_removed(self):
        result, tree, instructions = self.give('# Shared review standard\n\n- A rule.\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(instructions, 'existing rule\n\n# Shared review standard\n\n- A rule.\n')
        self.assertFalse((tree / '.review-shared').exists())

    def test_missing_or_empty_standard_stops_the_review(self):
        for standard in (None, '', '\n\n'):
            with self.subTest(standard=standard):
                result, _, instructions = self.give(standard)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(instructions, 'existing rule\n')


class SummaryTests(ScriptCase):
    def summary(self, conclusion='success', bodies=(), calls=None, record=None, reviewed='abc', head='abc', **env):
        comments = [{'user': {'login': 'github-actions[bot]'}, 'created_at': '2026-01-01T00:00:10Z', 'body': body}
                    for body in bodies]
        comments += [{'user': {'login': 'someone'}, 'created_at': '2026-01-01T00:00:10Z', 'body': '[High] not ours'},
                     {'user': {'login': 'github-actions[bot]'}, 'created_at': '2025-01-01T00:00:00Z', 'body': '[High] old'}]
        self.posted.write_text('', encoding='utf-8')
        api = self.dir / 'api.json'
        api.write_text(json.dumps(comments), encoding='utf-8')
        path = self.dir / 'record.json'
        if record is None:
            call = {'type': 'tool_use', 'name': comment_tool, 'input': {'body': 'text'}}
            record = json.dumps([{'type': 'assistant', 'message': {'content': [call] * (calls or 0)}}, used_result])
        path.write_text(record, encoding='utf-8')
        result = self.run_step('Post the review summary', CONCLUSION=conclusion, FAKE_API_JSON=str(api),
                               STARTED_AT='2026-01-01T00:00:00Z', EXECUTION_FILE=str(path), REVIEWED_SHA=reviewed,
                               FAKE_HEAD=head, RUN_URL='url', **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('syntax error', result.stderr)
        self.assertEqual(len(self.posts()), 1)
        return self.posts()[0]

    def test_counts_only_this_runs_comments_by_severity(self):
        text = self.summary(bodies=('[High] a', '[Medium] b', '[Low] c', '**No label**'))
        self.assertIn('Claude review posted 4 inline finding(s): 1 high, 1 medium, 1 low, 1 without a severity label.', text)
        self.assertIn('Commit: abc. [Run log](url)', text)

    def test_clean_run_finishes(self):
        self.assertTrue(self.summary().startswith('Claude review finished without posting any inline comments.'))

    def test_failed_run_says_whether_anything_posted(self):
        self.assertIn('did not complete, so this PR has not been reviewed', self.summary('failure'))

    def test_partial_run_is_marked_partial(self):
        self.assertIn('treat the review as partial', self.summary('', bodies=('[Low] a',)))

    def test_calls_with_nothing_posted_do_not_read_as_finished(self):
        text = self.summary(calls=2)
        self.assertTrue(text.startswith('Claude review made 2 comment call(s), but none posted.'), text)

    def test_shortfall_is_reported_without_calling_it_harmless(self):
        text = self.summary(bodies=('[High] a',), calls=3)
        self.assertIn('2 of 3 comment call(s) did not produce a posted comment', text)

    def test_moved_head_marks_the_review_stale_and_hides_the_new_commit(self):
        text = self.summary(head='newer')
        self.assertTrue(text.startswith('Claude review is stale:'), text)
        self.assertIn('Commit: abc.', text)
        self.assertNotIn('newer', text)

    def test_stale_warning_also_covers_a_failed_count(self):
        text = self.summary(head='newer', FAKE_API_FAILS='1')
        self.assertTrue(text.startswith('Claude review is stale:'), text)
        self.assertIn('could not be counted', text)

    def test_says_when_the_head_could_not_be_checked(self):
        text = self.summary(FAKE_HEAD_FAILS='1')
        self.assertIn('Head check unavailable. Commit: abc.', text)
        self.assertNotIn('stale', text)

    def test_unknown_commit_is_not_reported_as_moved(self):
        text = self.summary('failure', reviewed='', head='abc')
        self.assertIn('Commit: unknown.', text)
        self.assertNotIn('stale', text)

    def test_success_that_never_reached_the_model_is_not_a_review(self):
        # The action reports success even when the session ends before any model call.
        records = (json.dumps([unused_result]), json.dumps([{'type': 'result'}]), json.dumps([]), '', 'not json')
        for record in records:
            with self.subTest(record=record):
                text = self.summary(record=record)
                self.assertTrue(text.startswith('Claude review did not complete: its run record shows no call to the model,'), text)
                self.assertNotIn('finished', text)

    def test_calls_are_counted_across_a_multi_document_record(self):
        call = json.dumps([{'type': 'tool_use', 'name': comment_tool}])
        text = self.summary(record=f'{call}\n{call}\n')
        self.assertTrue(text.startswith('Claude review made 2 comment call(s), but none posted.'), text)

    def test_model_usage_is_found_in_a_multi_document_record(self):
        text = self.summary(record=f'{json.dumps([{"type": "assistant"}])}\n{json.dumps([used_result])}\n')
        self.assertTrue(text.startswith('Claude review finished without posting any inline comments.'), text)


class NoModelLogTests(ScriptCase):
    def log(self, content):
        path = self.dir / 'record.json'
        path.write_text(content, encoding='utf-8')
        result = self.run_step('Log why the session did not reach the model', EXECUTION_FILE=str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_shows_the_cli_message_when_the_model_was_never_called(self):
        out = self.log(json.dumps([{**unused_result, 'subtype': 'success', 'duration_ms': 1777, 'result': 'Unknown command'}]))
        self.assertIn('The session did not reach the model (success, 1777 ms): Unknown command', out)

    def test_never_shows_result_text_once_the_model_was_called(self):
        out = self.log(json.dumps([{**used_result, 'result': 'review text quoting the PR'}]))
        self.assertIn('The session reached the model.', out)
        self.assertNotIn('quoting the PR', out)

    def test_message_is_cut_to_500_characters(self):
        out = self.log(json.dumps([{**unused_result, 'result': 'x' * 600}]))
        self.assertIn('x' * 500 + '\n', out)
        self.assertNotIn('x' * 501, out)

    def test_says_when_there_is_nothing_to_show(self):
        self.assertIn('No run record.', self.log(''))
        self.assertIn('The run record could not be read.', self.log('not json'))
        self.assertIn('The run record has no result.', self.log(json.dumps([{'type': 'assistant'}])))


class DeniedToolsTests(ScriptCase):
    def denied(self, content):
        path = self.dir / 'record.json'
        path.write_text(content, encoding='utf-8')
        result = self.run_step('Log the tools that were denied', EXECUTION_FILE=str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_logs_names_and_counts_but_never_inputs(self):
        denials = [{'tool_name': 'Bash', 'tool_input': {'command': 'SECRET'}}, {'tool_name': 'Bash'}, {'tool_name': 'Grep'}]
        out = self.denied(json.dumps([{'type': 'result', 'permission_denials': denials}]))
        self.assertRegex(out, r'2 Bash')
        self.assertRegex(out, r'1 Grep')
        self.assertNotIn('SECRET', out)

    def test_says_when_nothing_was_denied_or_recorded(self):
        self.assertIn('No denied tools.', self.denied(json.dumps([{'type': 'result'}])))
        self.assertIn('No run record.', self.denied(''))


class CallerContractTests(unittest.TestCase):
    def test_caller_filter_matches_the_one_the_reusable_workflow_documents(self):
        text = caller.read_text(encoding='utf-8')
        expression = re.search(r'if: >-\n(.*?)\n\s*# The called', text, re.S).group(1)
        lines = workflow.read_text(encoding='utf-8').splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith('# Callers should use exactly this filter'))
        block = []
        for line in lines[start + 1:]:
            if not line.startswith('#   '):
                break
            block.append(line[1:])
        self.assertEqual(' '.join(expression.split()), ' '.join(' '.join(block).split()))

    def test_shared_standard_comes_from_this_workflows_own_commit(self):
        text = workflow.read_text(encoding='utf-8')
        step = text[text.index('- name: Check out the shared review standard'):]
        step = step[:step.index('\n\n')]
        self.assertIn('repository: ${{ job.workflow_repository }}', step)
        self.assertIn('ref: ${{ job.workflow_sha }}', step)
        self.assertIn('sparse-checkout: review/review-standard.md', step)
        self.assertLess(text.index('- name: Restore review rules from the default branch'), text.index('- name: Clear the shared standard\'s path'))
        self.assertLess(text.index('- name: Give the reviewer the shared review standard'), text.index('- id: review'))

    def test_review_prompt_is_only_the_skill_command(self):
        # Text after the command becomes part of the skill's review target.
        text = workflow.read_text(encoding='utf-8')
        self.assertRegex(text, r'prompt: /code-review high \$\{\{ env\.PR_NUMBER \}\} --comment --max-findings all\n')


class RepositoryTests(unittest.TestCase):
    def test_no_community_health_files(self):
        # GitHub applies a public .github repo's copies to every repo of the account that lacks its own.
        names = {'contributing', 'code_of_conduct', 'security', 'support', 'governance', 'funding',
                 'issue_template', 'pull_request_template', 'discussion_template'}
        for folder in (root, root / 'docs', root / '.github'):
            if not folder.is_dir():
                continue
            for entry in folder.iterdir():
                self.assertNotIn(entry.name.split('.')[0].lower(), names, entry)

    def test_shared_standard_exists_and_is_not_empty(self):
        self.assertTrue((root / 'review' / 'review-standard.md').read_text(encoding='utf-8').strip())


if __name__ == '__main__':
    unittest.main()
