"""Scoped source/CI contracts; no image build or host-policy changes required."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / '.github/workflows/image.yml').read_text()
DOCKERFILE = (ROOT / 'Dockerfile').read_text()
PUBLISH_GATE = "github.ref == 'refs/heads/main' && github.event_name != 'pull_request'"


def step(name):
    match = re.search(r'^      - name: ' + re.escape(name) + r'\n(.*?)(?=^      - |^  \w|\Z)',
                      WORKFLOW, re.M | re.S)
    if not match:
        raise AssertionError('Missing workflow step: ' + name)
    return match.group(1)


class DependencyPolicyTests(unittest.TestCase):
    def test_weekly_schedule_and_existing_triggers(self):
        self.assertIn("  schedule:\n    - cron: '3 6 * * 1'\n", WORKFLOW)
        self.assertIn('  pull_request:\n', WORKFLOW)
        self.assertIn('  push:\n    branches: [main]\n', WORKFLOW)
        self.assertIn('  workflow_dispatch:\n', WORKFLOW)

    def test_all_publication_gates_allow_main_push_manual_schedule_only(self):
        gates = re.findall(r'^\s+if: (.*)$', step('Export exact tested runtime'), re.M)
        gates += re.findall(r'^\s+if: (.*)$', step('Retain runtime for publisher'), re.M)
        publisher = WORKFLOW.split('  publish:\n', 1)[1]
        gates += re.findall(r'^    if: (.*)$', publisher, re.M)
        self.assertEqual(gates, [PUBLISH_GATE] * 3)
        # Evaluate the actual limited expression, without eval or a YAML dependency.
        for gate in gates:
            ref_key, eq, main, conjunction, event_key, ne, pr = shlex.split(gate)
            self.assertEqual((ref_key, eq, conjunction, event_key, ne),
                             ('github.ref', '==', '&&', 'github.event_name', '!='))
            for event in ('push', 'workflow_dispatch', 'schedule', 'pull_request'):
                for ref in ('refs/heads/main', 'refs/heads/topic', 'refs/pull/1/merge', 'refs/tags/v1'):
                    with self.subTest(event=event, ref=ref):
                        self.assertEqual(ref == main and event != pr,
                                         ref == 'refs/heads/main' and event != 'pull_request')

    def test_immutable_official_base_and_real_package_refresh(self):
        base = step('Resolve current official base to immutable digest')
        self.assertIn('BASE: ghcr.io/games-on-whales/base-app:fedora', base)
        self.assertIn('docker pull --platform linux/amd64 "$BASE"', base)
        self.assertIn("--format '{{index .RepoDigests 0}}'", base)
        self.assertIn('echo "BASE_IMAGE=$reference"', base)
        self.assertIn('echo "BASE_DIGEST=${reference#*@}"', base)
        build = step('Build runtime and disposable test target').replace('\\\n', ' ')
        commands = [shlex.split(line.strip()) for line in build.splitlines()
                    if line.strip().startswith('docker buildx build ')]
        self.assertEqual(len(commands), 2)
        for command, target in zip(commands, ('runtime', 'test')):
            for flag in ('--pull', '--load'):
                self.assertIn(flag, command)
            self.assertEqual(command[command.index('--platform') + 1], 'linux/amd64')
            self.assertEqual(command[command.index('--target') + 1], target)
            self.assertIn('BASE_IMAGE=$BASE_IMAGE', command)
            self.assertIn('BASE_DIGEST=$BASE_DIGEST', command)
        self.assertEqual(commands[0][commands[0].index('--no-cache-filter') + 1],
                         'xwayland,runtime-deps,runtime')
        self.assertNotIn('--no-cache-filter', commands[1])
        self.assertNotIn('--no-cache', commands[1])

    def test_same_release_upgrade_and_eol_fail_closed_in_both_package_stages(self):
        for stage in ('xwayland', 'runtime-deps'):
            body = re.search(r'^FROM .* AS ' + stage + r'\n(.*?)(?=^FROM |\Z)',
                             DOCKERFILE, re.M | re.S).group(1)
            guard = re.search(r'^RUN (source /etc/os-release.*?)dnf upgrade',
                              body, re.M | re.S).group(1).replace('\\\n', ' ')
            self.assertIn('dnf upgrade -y --refresh --setopt=install_weak_deps=False', body)
            self.assertNotRegex(body, r'--releasever|--nogpgcheck|gpgcheck=0|system-upgrade|copr enable')
            # Execute the Dockerfile's actual guard against disposable release files.
            guard = guard.replace('source /etc/os-release', 'source "$1"') + 'true'
            today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            for release, expected in (
                ('ID=fedora\nSUPPORT_END=2999-01-01\n', True),
                ('ID=fedora\nSUPPORT_END=2000-01-01\n', False),
                (f'ID=fedora\nSUPPORT_END={today}\n', False),
                ('ID=fedora\n', False),
                ('ID=other\nSUPPORT_END=2999-01-01\n', False),
            ):
                with self.subTest(stage=stage, release=release), tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / 'os-release'
                    path.write_text(release)
                    result = subprocess.run(['bash', '-u', '-c', guard, 'guard', str(path)],
                                            capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode == 0, expected, result.stderr)

    def test_private_xwayland_source_and_fail_closed_guard_retained(self):
        self.assertIn('xwayland-24.1.14.tar.xz', DOCKERFILE)
        self.assertIn('4eb6b98d678299a4b96138d886345b294130695760345ef84596225a8224078a', DOCKERFILE)
        self.assertIn('patch --fuzz=0 -p1 -d xwayland-24.1.14', DOCKERFILE)
        self.assertRegex(DOCKERFILE, r'test "\$\(rpm --eval .*xorg-x11-server-Xwayland.*24\.1\.14.* -le 0 &&')

    def test_candidate_evidence_uses_exact_runtime_not_upstream_claims(self):
        evidence = step('Record candidate runtime versions and base provenance')
        self.assertIn('docker image inspect wolf-lutris:local-review', evidence)
        self.assertIn('docker run --rm --network none --entrypoint bash wolf-lutris:local-review', evidence)
        for command in ('cat /etc/os-release',
                        'rpm -q lutris wine-core.x86_64 wine-core.i686 xorg-x11-server-Xwayland',
                        '/usr/local/libexec/wolf-lutris/Xwayland -version'):
            self.assertIn(command, evidence)
        retained = step('Retain software acceptance logs')
        self.assertIn('if: always()', retained)
        self.assertIn('path: artifacts/', retained)

    def test_runtime_contract_accepts_supported_release_without_historical_os_pin(self):
        spec = importlib.util.spec_from_file_location('image_contract', ROOT / 'tests/image-contract.py')
        contract = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(contract)
        for version in ('44', '45'):
            contract.require_supported_release({'ID': 'fedora', 'VERSION_ID': version, 'SUPPORT_END': '2999-01-01'})
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        for release in ({'ID': 'other', 'SUPPORT_END': '2999-01-01'},
                        {'ID': 'fedora'}, {'ID': 'fedora', 'SUPPORT_END': today},
                        {'ID': 'fedora', 'SUPPORT_END': '2000-01-01'}):
            with self.subTest(release=release), self.assertRaises((AssertionError, KeyError)):
                contract.require_supported_release(release)

    def test_runtime_version_floor_allows_updates_but_rejects_regression(self):
        spec = importlib.util.spec_from_file_location('image_contract', ROOT / 'tests/image-contract.py')
        contract = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(contract)
        for version, comparison in (('0.5.22', '0'), ('0.5.23', '1')):
            with patch.object(contract, 'run', side_effect=[version, comparison]) as run:
                contract.require_minimum_version('lutris', '0.5.22')
                self.assertEqual(run.call_args.args, ('rpm', '--eval',
                                 f'%{{lua: print(rpm.vercmp("{version}", "0.5.22"))}}'))
        with patch.object(contract, 'run', side_effect=['0.5.21', '-1']), self.assertRaises(AssertionError):
            contract.require_minimum_version('lutris', '0.5.22')

    def test_required_acceptance_before_exact_runtime_export_and_no_publish_rebuild(self):
        checks = step('Runtime contract and software integration checks')
        self.assertIn('bash tests/run.sh wolf-lutris:test', checks)
        self.assertIn('bash tests/runtime-image.sh wolf-lutris:local-review', checks)
        self.assertNotIn('if:', checks)
        self.assertNotIn('continue-on-error', WORKFLOW)
        self.assertLess(WORKFLOW.index('name: Runtime contract and software integration checks'),
                        WORKFLOW.index('name: Export exact tested runtime'))
        self.assertIn('docker save wolf-lutris:local-review | gzip > tested-image.tar.gz',
                      step('Export exact tested runtime'))
        publisher = WORKFLOW.split('  publish:\n', 1)[1]
        self.assertIn('needs: image', publisher)
        self.assertIn('docker load --input tested-image.tar.gz', publisher)
        self.assertIn('docker tag wolf-lutris:local-review "$IMAGE:$tag"', publisher)
        self.assertIn('latest "sha-$GITHUB_SHA-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"', publisher)
        self.assertNotRegex(publisher, r'docker build|build-push-action')


if __name__ == '__main__':
    unittest.main()
