import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class AgentInstallTests(unittest.TestCase):
    def load(self,name,path):
        self.assertTrue(path.is_file(),'agent installation helper is missing')
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_trae_command_has_no_spaces_when_install_directory_has_spaces(self):
        module=self.load('installer',ROOT/'installer.py')
        with tempfile.TemporaryDirectory(prefix='agent path ') as td:
            root=Path(td)/'中文 空格'
            configs=module.generate_configs(root,root/'.venv/Scripts/python.exe','win32')
            servers=json.loads(configs['trae/mcp.json'])['mcpServers']
            for route in ('jd','symc'):
                server=servers['shopdate-'+route]
                self.assertNotIn(' ',server['command'])
                self.assertTrue(any(str(x).endswith('launch_venv_mcp.py') for x in server['args']))
                self.assertEqual(server['args'][-1],route)

    def test_project_merge_preserves_other_entries_and_original_text(self):
        module=self.load('register',ROOT/'scripts/register_project.py')
        raw='{\r\n\t"other": { "keep" : 1 },\r\n\t"mcpServers": {\r\n\t\t"existing": { "command" : "keep-me" }\r\n\t}\r\n}\r\n'
        updated=module.merge_text(raw,{'shopdate-jd':{'command':'python','args':['mcp']}})
        self.assertIn('"other": { "keep" : 1 }',updated)
        self.assertIn('"existing": { "command" : "keep-me" }',updated)
        self.assertNotIn('\n',updated.replace('\r\n',''))
        self.assertEqual(json.loads(updated)['mcpServers']['existing']['command'],'keep-me')
        self.assertEqual(module.merge_text(updated,{'shopdate-jd':{'command':'python','args':['mcp']}}),updated)

    def test_native_trae_servers_schema_is_preserved(self):
        module=self.load('register',ROOT/'scripts/register_project.py')
        raw='{"servers":{"existing":{"command":"keep"}},"inputs":[]}'
        value=json.loads(module.merge_text(raw,{'shopdate-jd':{'command':'python'}}))
        self.assertNotIn('mcpServers',value)
        self.assertEqual(value['inputs'],[])
        self.assertEqual(set(value['servers']),{'existing','shopdate-jd'})

    def test_conflict_or_jsonc_never_changes_target(self):
        module=self.load('register',ROOT/'scripts/register_project.py')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'mcp.json';before=b'{"mcpServers":{"shopdate-jd":{"command":"other"}}}'
            p.write_bytes(before)
            with self.assertRaises(ValueError):module.register(p,{'shopdate-jd':{'command':'python'}},Path(td)/'backups')
            self.assertEqual(p.read_bytes(),before)
            p.write_text('{// comment\n"mcpServers":{}}',encoding='utf-8')
            with self.assertRaises(ValueError):module.register(p,{'shopdate-jd':{'command':'python'}},Path(td)/'backups')
            self.assertIn('// comment',p.read_text())

    def test_backup_is_exact_and_idempotent_registration_has_no_new_backup(self):
        module=self.load('register',ROOT/'scripts/register_project.py')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'mcp.json';before=b'\xef\xbb\xbf{ "unrelated": true }\r\n';p.write_bytes(before)
            backup_dir=Path(td)/'backups';new={'shopdate-jd':{'command':'python'}}
            result=module.register(p,new,backup_dir)
            self.assertTrue(result['changed'])
            self.assertEqual(Path(result['backup']).read_bytes(),before)
            self.assertTrue(p.read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertFalse(module.register(p,new,backup_dir)['changed'])
            self.assertEqual(len(list(backup_dir.iterdir())),1)


if __name__=='__main__':unittest.main()
