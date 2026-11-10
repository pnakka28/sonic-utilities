import sys
import os
import importlib
import importlib.machinery
import importlib.util
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest import mock
from click.testing import CliRunner
from unittest import TestCase

test_path = os.path.dirname(os.path.abspath(__file__))
modules_path = os.path.dirname(test_path)
scripts_path = os.path.join(modules_path, "scripts")
sys.path.insert(0, test_path)
sys.path.insert(0, modules_path)

from .mock_tables import dbconnector

import show.main as show

# Load gearboxutil script as a module for direct function testing
# spec_from_file_location returns None for extensionless scripts; use SourceFileLoader explicitly
_gearboxutil_loader = importlib.machinery.SourceFileLoader(
    "gearboxutil", os.path.join(scripts_path, "gearboxutil"))
_gearboxutil_spec = importlib.util.spec_from_loader("gearboxutil", _gearboxutil_loader)
gearboxutil = importlib.util.module_from_spec(_gearboxutil_spec)
_gearboxutil_loader.exec_module(gearboxutil)

class TestGearbox(TestCase):
    @classmethod
    def setup_class(cls):
        print("SETUP")
        os.environ["UTILITIES_UNIT_TESTING"] = "1"

    def setUp(self):
        self.runner = CliRunner()

    def test_gearbox_phys_status_validation(self):
        result = self.runner.invoke(show.cli.commands["gearbox"].commands["phys"].commands["status"], [])
        print(result.output, file=sys.stderr)
        expected_output = (
            "PHY Id     Name    Firmware\n"
            "--------  -------  ----------\n"
            "       1  sesto-1        v0.2\n"
            "       2  sesto-2        v0.3"
        )
        self.assertEqual(result.output.strip(), expected_output)

    def test_gearbox_interfaces_status_validation(self):
        result = self.runner.invoke(show.cli.commands["gearbox"].commands["interfaces"].commands["status"], [])
        print(result.output, file=sys.stderr)
        expected_output = (
            "PHY Id    Interface        MAC Lanes    MAC Lane Speed        PHY Lanes    PHY Lane Speed    Line Lanes    Line Lane Speed    Oper    Admin\n"
            "--------  -----------  ---------------  ----------------  ---------------  ----------------  ------------  -----------------  ------  -------\n"
            "       1  Ethernet200  200,201,202,203               25G  300,301,302,303               25G       304,305                50G    down       up"
        )
        self.assertEqual(result.output.strip(), expected_output)

    def test_gearbox_interfaces_fec_stats(self):
        result = self.runner.invoke(
            show.cli.commands["gearbox"].commands["interfaces"].commands["fec-stats"], ["Ethernet0"])
        print(result.output, file=sys.stderr)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("FEC_CORR", result.output)
        self.assertIn("Ethernet0 Line", result.output)
        self.assertIn("Ethernet0 System", result.output)

    def test_gearbox_interfaces_fec_histogram(self):
        result = self.runner.invoke(
            show.cli.commands["gearbox"].commands["interfaces"].commands["fec-histogram"], ["Ethernet0"])
        print(result.output, file=sys.stderr)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Ethernet0", result.output)
        self.assertIn("BIN0", result.output)
        self.assertIn("BIN15", result.output)

    @classmethod
    def teardown_class(cls):
        print("TEARDOWN")
        os.environ["PATH"] = os.pathsep.join(os.environ["PATH"].split(os.pathsep)[:-1])
        os.environ["UTILITIES_UNIT_TESTING"] = "0"


class TestFormatBer(TestCase):
    def test_normal_value(self):
        self.assertEqual(gearboxutil.format_ber("6.05e-10"), "6.05e-10")

    def test_small_nonzero_value(self):
        self.assertEqual(gearboxutil.format_ber("0.000000000605"), "6.05e-10")

    def test_zero(self):
        self.assertEqual(gearboxutil.format_ber("0"), "0.00e+00")

    def test_na_passthrough(self):
        self.assertEqual(gearboxutil.format_ber("N/A"), "N/A")

    def test_minus_one_passthrough(self):
        self.assertEqual(gearboxutil.format_ber("-1"), "-1")

    def test_non_numeric_passthrough(self):
        self.assertEqual(gearboxutil.format_ber("invalid"), "invalid")


class TestInterfaceFecStats(TestCase):
    @classmethod
    def setup_class(cls):
        os.environ["UTILITIES_UNIT_TESTING"] = "1"
        dbconnector.load_database_config()

    def _capture(self, port_name=None, display_type='stats'):
        buf = StringIO()
        with redirect_stdout(buf):
            gearboxutil.InterfaceFecStats(port_name=port_name, display_type=display_type)
        return buf.getvalue()

    def test_fec_stats_all_ports_headers(self):
        output = self._capture(display_type='stats')
        for col in ['GB IFACE', 'STATE', 'FEC_CORR', 'FEC_UNCORR', 'FEC_SYMBOL_ERR',
                    'FEC_PRE_BER', 'FEC_POST_BER', 'FEC_PRE_BER_MAX', 'FEC_MAX_T']:
            self.assertIn(col, output)

    def test_fec_stats_all_ports_contains_ethernet0(self):
        output = self._capture(display_type='stats')
        self.assertIn("Ethernet0", output)

    def test_fec_stats_formatted_ber(self):
        output = self._capture(display_type='stats')
        self.assertIn("6.05e-10", output)

    def test_fec_stats_specific_port(self):
        output = self._capture(port_name="Ethernet0", display_type='stats')
        self.assertIn("Ethernet0", output)
        self.assertIn("FEC_CORR", output)

    def test_fec_stats_invalid_port(self):
        output = self._capture(port_name="EthernetInvalid", display_type='stats')
        self.assertIn("Error", output)
        self.assertIn("EthernetInvalid", output)

    def test_fec_stats_state_uses_system_and_line_oper_status(self):
        # Mock has system_oper_status=up -> 'U' and line_oper_status=down -> 'D'
        # Verifies get_port_state reads the correct per-side field, not generic oper_status
        output = self._capture(port_name="Ethernet0", display_type='stats')
        lines = [row for row in output.splitlines() if "Ethernet0" in row]
        system_line = next((row for row in lines if "System" in row), None)
        line_line = next((row for row in lines if "Line" in row), None)
        self.assertIsNotNone(system_line, "Expected a System row in fec-stats output")
        self.assertIsNotNone(line_line, "Expected a Line row in fec-stats output")
        self.assertIn("U", system_line, "System side should show U (system_oper_status=up)")
        self.assertIn("D", line_line, "Line side should show D (line_oper_status=down)")

    def test_fec_histogram_all_ports_bins(self):
        output = self._capture(display_type='histogram')
        self.assertIn("Ethernet0", output)
        for i in range(16):
            self.assertIn(f"BIN{i}", output)

    def test_fec_histogram_specific_port(self):
        output = self._capture(port_name="Ethernet0", display_type='histogram')
        self.assertIn("Ethernet0", output)
        self.assertIn("BIN0", output)

    def test_fec_histogram_invalid_port(self):
        output = self._capture(port_name="EthernetInvalid", display_type='histogram')
        self.assertIn("Error", output)

    def test_fec_histogram_last_updated_header(self):
        output = self._capture(port_name="Ethernet0", display_type='histogram')
        self.assertIn("Last Updated", output)

    def test_fec_histogram_timestamp_formatted(self):
        # Mock has S0_TIMESTAMP set to a non-zero ms value; format it the same way the script does
        from datetime import datetime as _dt
        ts_ms = 1716579600000
        expected = _dt.fromtimestamp(ts_ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")
        output = self._capture(port_name="Ethernet0", display_type='histogram')
        self.assertIn(expected, output)

    def test_fec_histogram_zero_and_missing_timestamps_render_na(self):
        # S1_TIMESTAMP is "0" (sentinel) and S2..S15 have no *_TIMESTAMP entry; all must render as N/A
        output = self._capture(port_name="Ethernet0", display_type='histogram')
        self.assertIn("N/A", output)

    def test_fec_stats_single_asic_has_no_asic_column(self):
        output = self._capture(display_type='stats')
        self.assertNotIn("ASIC", output.splitlines()[0])

    @classmethod
    def teardown_class(cls):
        os.environ["UTILITIES_UNIT_TESTING"] = "0"


def _rows(output):
    """Split each output line into whitespace separated tokens"""
    return [line.split() for line in output.splitlines() if line.strip()]


class TestGearboxMultiAsic(object):
    """
    Mock multi-ASIC layout: asic0 (front-end) has a gearbox PHY on Ethernet0 and
    asic1 (back-end) has a gearbox PHY on backplane port Ethernet-BP256; both use PHY id 1.
    """

    @classmethod
    def setup_class(cls):
        os.environ["UTILITIES_UNIT_TESTING"] = "1"
        os.environ["UTILITIES_UNIT_TESTING_TOPOLOGY"] = "multi_asic"
        from .mock_tables import mock_multi_asic
        importlib.reload(mock_multi_asic)
        dbconnector.load_namespace_config()

    def invoke(self, *path, args=None):
        command = show.cli.commands["gearbox"]
        for name in path:
            command = command.commands[name]
        result = CliRunner().invoke(command, args or [])
        print(result.output, file=sys.stderr)
        assert result.exit_code == 0
        return result.output

    def test_is_gearbox_configured_checks_asic_namespaces(self):
        assert show.is_gearbox_configured()

    def test_is_gearbox_configured_no_gearbox_in_any_namespace(self):
        with mock.patch('sonic_py_common.multi_asic.get_namespace_list', return_value=['asic2']):
            assert not show.is_gearbox_configured()

    def test_is_gearbox_configured_skips_unreachable_namespace(self):
        real_connector = show.SonicV2Connector

        def connector(*args, **kwargs):
            if kwargs.get('namespace') == 'asic0':
                raise RuntimeError("Unable to connect to redis")
            return real_connector(*args, **kwargs)

        # asic1 still has a gearbox PHY
        with mock.patch('show.main.SonicV2Connector', side_effect=connector):
            assert show.is_gearbox_configured()

    def test_is_gearbox_configured_skips_fabric_namespaces(self):
        all_namespaces = {'front_ns': ['asic2'], 'back_ns': [], 'fabric_ns': ['asic0', 'asic1']}
        with mock.patch('sonic_py_common.multi_asic.get_namespace_list', return_value=['asic0', 'asic1', 'asic2']), \
                mock.patch('sonic_py_common.multi_asic.get_all_namespaces', return_value=all_namespaces):
            assert not show.is_gearbox_configured()

    def test_gearboxutil_namespace_list_excludes_fabric(self):
        all_namespaces = {'front_ns': ['asic0'], 'back_ns': ['asic1'], 'fabric_ns': ['asic2']}
        with mock.patch('sonic_py_common.multi_asic.get_all_namespaces', return_value=all_namespaces):
            assert gearboxutil.get_namespace_list() == ['asic0', 'asic1']
            assert gearboxutil.get_namespace_list('asic2') == ['asic2']

    def test_gearboxutil_skips_unreachable_namespace(self):
        real_connector = gearboxutil.SonicV2Connector

        def connector(*args, **kwargs):
            if kwargs.get('namespace') == 'asic0':
                raise RuntimeError("Unable to connect to redis")
            return real_connector(*args, **kwargs)

        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err), \
                mock.patch.object(gearboxutil, 'SonicV2Connector', side_effect=connector):
            gearboxutil.PhyStatus(namespaces=['asic0', 'asic1'], show_asic=True)
            gearboxutil.InterfaceFecStats(display_type='stats', namespaces=['asic0', 'asic1'], show_asic=True)
        rows = _rows(out.getvalue())
        assert ['asic1', '1', 'agera3-1', 'v1.1'] in rows
        assert ['asic1', 'Ethernet-BP256', 'Line'] in [row[:3] for row in rows]
        assert not any(row[0] == 'asic0' for row in rows)
        assert "failed to connect to APPL_DB in namespace 'asic0'" in err.getvalue()

    def test_phys_status(self):
        rows = _rows(self.invoke("phys", "status"))
        assert rows[0] == ['ASIC', 'PHY', 'Id', 'Name', 'Firmware']
        assert rows[2:] == [['asic0', '1', 'agera3-0', 'v1.0'],
                            ['asic1', '1', 'agera3-1', 'v1.1']]

    def test_phys_status_namespace(self):
        rows = _rows(self.invoke("phys", "status", args=["-n", "asic1"]))
        assert rows[2:] == [['asic1', '1', 'agera3-1', 'v1.1']]

    def test_interfaces_status(self):
        rows = _rows(self.invoke("interfaces", "status"))
        assert rows[0][:3] == ['ASIC', 'PHY', 'Id']
        assert rows[2:] == [
            ['asic0', '1', 'Ethernet0', '33,34,35,36', '10G', '100,101,102,103', '40G',
             '200,201,202,203', '40G', 'up', 'up'],
            ['asic1', '1', 'Ethernet-BP256', '61,62,63,64', '10G', '400,401,402,403', '40G',
             '300,301,302,303', '40G', 'up', 'up'],
        ]

    def test_interfaces_status_namespace(self):
        rows = _rows(self.invoke("interfaces", "status", args=["-n", "asic0"]))
        assert [row[:3] for row in rows[2:]] == [['asic0', '1', 'Ethernet0']]

    def test_fec_stats(self):
        rows = _rows(self.invoke("interfaces", "fec-stats"))
        assert rows[0][:3] == ['ASIC', 'GB', 'IFACE']
        assert [row[:6] for row in rows[2:]] == [
            ['asic0', 'Ethernet0', 'Line', 'N/A', '2,000', '1'],
            ['asic0', 'Ethernet0', 'System', 'N/A', '1,000', '0'],
            ['asic1', 'Ethernet-BP256', 'Line', 'N/A', '4,000', '1'],
            ['asic1', 'Ethernet-BP256', 'System', 'N/A', '3,000', '0'],
        ]

    def test_fec_stats_namespace(self):
        rows = _rows(self.invoke("interfaces", "fec-stats", args=["-n", "asic1"]))
        assert {row[0] for row in rows[2:]} == {'asic1'}
        assert len(rows[2:]) == 2

    def test_fec_stats_port_on_backend_asic(self):
        rows = _rows(self.invoke("interfaces", "fec-stats", args=["Ethernet-BP256"]))
        assert [row[:3] for row in rows[2:]] == [['asic1', 'Ethernet-BP256', 'Line'],
                                                 ['asic1', 'Ethernet-BP256', 'System']]

    def test_fec_stats_port_not_in_namespace(self):
        output = self.invoke("interfaces", "fec-stats", args=["Ethernet-BP256", "-n", "asic0"])
        assert "Error: Port 'Ethernet-BP256' not found in GB_COUNTERS_DB" in output
        assert "Available ports: Ethernet0" in output

    def test_fec_stats_invalid_port_lists_ports_of_all_asics(self):
        output = self.invoke("interfaces", "fec-stats", args=["EthernetInvalid"])
        assert "Available ports: Ethernet0, Ethernet-BP256" in output

    def test_fec_histogram_port(self):
        output = self.invoke("interfaces", "fec-histogram", args=["Ethernet-BP256"])
        assert "Ethernet-BP256 Line (asic1)" in output
        assert "Ethernet-BP256 System (asic1)" in output
        assert "BIN15" in output

    def test_invalid_namespace(self):
        result = CliRunner().invoke(
            show.cli.commands["gearbox"].commands["phys"].commands["status"], ["-n", "asic9"])
        assert result.exit_code != 0

    def test_gearboxutil_invalid_namespace(self):
        buf = StringIO()
        with redirect_stdout(buf), mock.patch.object(sys, 'exit', side_effect=SystemExit) as mock_exit:
            try:
                gearboxutil.main(['-n', 'asic9', 'phys', 'status'])
            except SystemExit:
                pass
        mock_exit.assert_called_with(1)
        assert "Unknown Namespace asic9" in buf.getvalue()

    def test_gearboxutil_namespace_option_missing_value(self):
        buf = StringIO()
        with redirect_stdout(buf), mock.patch.object(sys, 'exit', side_effect=SystemExit) as mock_exit:
            try:
                gearboxutil.main(['phys', 'status', '-n'])
            except SystemExit:
                pass
        mock_exit.assert_called_with(1)
        assert "-n/--namespace requires a namespace name" in buf.getvalue()

    @classmethod
    def teardown_class(cls):
        os.environ["UTILITIES_UNIT_TESTING"] = "0"
        os.environ["UTILITIES_UNIT_TESTING_TOPOLOGY"] = ""
        from .mock_tables import mock_single_asic
        importlib.reload(mock_single_asic)
        dbconnector.load_database_config()
