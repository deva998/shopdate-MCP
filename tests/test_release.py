"""Offline release tests: no browser, account access or business requests."""
import importlib.util
import json
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def installer(self):
        path = ROOT / 'installer.py'
        self.assertTrue(path.is_file(), 'portable installer has not been implemented')
        spec = importlib.util.spec_from_file_location('shopdate_installer', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_clients_use_absolute_python_and_same_public_launcher(self):
        module = self.installer()
        with tempfile.TemporaryDirectory(prefix='shopdate space ') as td:
            root = Path(td) / '中文目录'
            py = root / '.venv' / 'bin' / 'python'
            configs = module.generate_configs(root, py, 'darwin')
            generic = json.loads(configs['generic/mcp.json'])['mcpServers']
            self.assertEqual(set(generic), {'shopdate-jd', 'shopdate-symc'})
            for key, value in generic.items():
                self.assertEqual(value['command'], str(py.resolve()))
                self.assertEqual(value['args'][0], str((root / 'shopdate.py').resolve()))
                self.assertEqual(value['args'][-1], 'mcp')
                self.assertTrue(all(isinstance(v, str) for v in value['env'].values()))
                self.assertEqual(value['env']['SYCM_MODE'], 'extension')
            trae = json.loads(configs['trae/mcp.json'])['mcpServers']
            self.assertEqual(trae['shopdate-jd']['env']['RUN_MCP_TIMEOUT_MS'], '600000')
            for route in ('jd', 'symc'):
                workbuddy = json.loads(configs[f'workbuddy/shopdate-{route}/mcp.json'])['mcpServers']
                self.assertEqual(list(workbuddy), [f'shopdate-{route}'])
            codex = tomllib.loads(configs['codex/config.toml'])['mcp_servers']
            self.assertEqual(codex['shopdate-symc']['command'], str(py.resolve()))
            self.assertNotIn('enabled_tools', codex['shopdate-symc'])

    def test_config_export_never_overwrites_existing_export_or_client(self):
        module = self.installer()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = module.export_configs(root, root/'python', 'win32', 'all')
            original = (first/'generic/mcp.json').read_bytes()
            second = module.export_configs(root, root/'python', 'win32', 'all')
            self.assertNotEqual(first, second)
            self.assertEqual((first/'generic/mcp.json').read_bytes(), original)
            self.assertFalse((root/'.codex').exists())

    def test_ali_route_is_relative_to_bundle_and_not_current_directory(self):
        module = self.installer()
        self.assertEqual(module.source_roots(ROOT)['ali'], (ROOT/'components/ali').resolve())
        for name in ('shopdate_cli.py', 'shopdate_workflows/source.py', 'shopdate_workflows/ad_source_live.py'):
            content = (ROOT/'components/jd'/name).read_text(encoding='utf-8')
            self.assertNotIn("['symc_root']", content)
            self.assertIn("ROOT.parent/'ali'", content)

    def test_both_mcp_servers_receive_mcp_only_rule(self):
        self.installer()
        for platform in ('jd','ali'):
            content = (ROOT/f'components/{platform}/tb/mcp_server.py').read_text(encoding='utf-8')
            self.assertIn('不使用 Computer Use', content)
            self.assertIn('明确列为缺口', content)

    def test_root_git_metadata_is_excluded_but_nested_repositories_are_rejected(self):
        spec=importlib.util.spec_from_file_location('audit_git', ROOT/'scripts/verify_release.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'.git').mkdir();(root/'.git/config').write_text('private git metadata')
            (root/'README.md').write_text('public source')
            self.assertEqual(module.audit(root), [])
            self.assertEqual(set(module.inventory(root)), {'README.md'})
            (root/'nested/.git').mkdir(parents=True)
            (root/'nested/.git/config').write_text('nested repository')
            self.assertTrue(any(x['rule']=='forbidden_path' for x in module.audit(root)))

    def test_auditor_rejects_runtime_and_user_specific_content(self):
        spec = importlib.util.spec_from_file_location('audit', ROOT/'scripts/verify_release.py')
        self.assertIsNotNone(spec)
        self.assertTrue(Path(spec.origin).is_file(), 'release auditor has not been implemented')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'.runtime').mkdir()
            (root/'.runtime'/'account.json').write_text('{}')
            (root/'bad.txt').write_text('C:/'+'Users/example/private\n-----BEGIN '+'PRIVATE KEY-----', encoding='utf-8')
            findings = module.audit(root)
            self.assertTrue(any(x['rule']=='forbidden_path' for x in findings))
            self.assertTrue(any(x['rule']=='personal_path' for x in findings))
            self.assertTrue(any(x['rule']=='private_key' for x in findings))

    def test_offline_install_requires_local_wheelhouse(self):
        module = self.installer()
        with self.assertRaisesRegex(ValueError, 'wheelhouse'):
            module.validate_options(offline=True, wheelhouse=None)

    def test_installer_rejects_32_bit_python_before_dependency_install(self):
        module = self.installer()
        self.assertTrue(hasattr(module, 'validate_runtime'), 'runtime validation has not been implemented')
        with self.assertRaisesRegex(ValueError, '64'):
            module.validate_runtime((3, 12), 32)
        with self.assertRaisesRegex(ValueError, '3.11'):
            module.validate_runtime((3, 10), 64)
        module.validate_runtime((3, 11), 64)

    def test_static_macos_examples_use_posix_virtual_environment(self):
        self.installer()
        for path in (ROOT/'mcp-configs/examples/macos').rglob('*'):
            if path.suffix == '.json':
                servers = json.loads(path.read_text(encoding='utf-8'))['mcpServers']
            elif path.suffix == '.toml':
                servers = tomllib.loads(path.read_text(encoding='utf-8'))['mcp_servers']
            else:
                continue
            for server in servers.values():
                self.assertEqual(server['command'], '/SHOPDATE/.venv/bin/python')
                self.assertEqual(server['args'][0], '/SHOPDATE/shopdate.py')
                self.assertNotIn('\\', json.dumps(server))

    def test_online_mode_overrides_inherited_no_index_without_mutating_parent(self):
        module = self.installer()
        self.assertTrue(hasattr(module, 'pip_environment'), 'pip mode isolation is missing')
        inherited = {'PIP_NO_INDEX':'1','PIP_INDEX_URL':'https://pypi.org/simple','HTTPS_PROXY':'test-proxy'}
        actual = module.pip_environment(False, inherited)
        self.assertEqual(actual['PIP_NO_INDEX'], '0')
        self.assertEqual(actual['PIP_INDEX_URL'], inherited['PIP_INDEX_URL'])
        self.assertEqual(actual['HTTPS_PROXY'], inherited['HTTPS_PROXY'])
        self.assertEqual(inherited['PIP_NO_INDEX'], '1')

    def test_offline_mode_remains_offline_when_parent_enables_index(self):
        module = self.installer()
        self.assertTrue(hasattr(module, 'pip_environment'), 'pip mode isolation is missing')
        self.assertEqual(module.pip_environment(True, {'PIP_NO_INDEX':'0'})['PIP_NO_INDEX'], '1')

    def test_explicit_index_is_https_and_incompatible_with_offline(self):
        module = self.installer()
        self.assertTrue(hasattr(module, 'pip_command'), 'explicit pip index support is missing')
        good = 'https://pypi.tuna.tsinghua.edu.cn/simple'
        module.validate_options(offline=False, wheelhouse=None, index_url=good)
        for bad in ('http://example.test/simple','file:///tmp/packages','https://user:secret@example.test/simple'):
            with self.assertRaises(ValueError):
                module.validate_options(offline=False, wheelhouse=None, index_url=bad)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                module.validate_options(offline=True, wheelhouse=Path(td), index_url=good)

    def test_explicit_index_reaches_pip_without_disabling_tls(self):
        module = self.installer()
        self.assertTrue(hasattr(module, 'pip_command'), 'explicit pip index support is missing')
        index = 'https://pypi.tuna.tsinghua.edu.cn/simple'
        cmd = module.pip_command(Path('python'), Path('requirements.txt'), index_url=index)
        self.assertEqual(cmd[cmd.index('--index-url')+1], index)
        self.assertNotIn('--trusted-host', cmd)
        self.assertNotIn('--no-index', cmd)


if __name__ == '__main__':
    unittest.main()
