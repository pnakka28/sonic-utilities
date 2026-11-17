import sys
import os
import json
import importlib.machinery
import importlib.util
from contextlib import redirect_stdout
from io import StringIO
from click.testing import CliRunner
from unittest import TestCase, mock

test_path = os.path.dirname(os.path.abspath(__file__))
modules_path = os.path.dirname(test_path)
scripts_path = os.path.join(modules_path, "scripts")
sys.path.insert(0, test_path)
sys.path.insert(0, modules_path)

from .mock_tables import dbconnector

import show.main as show
import clear.main as clear  # noqa: E402

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

    @classmethod
    def teardown_class(cls):
        os.environ["UTILITIES_UNIT_TESTING"] = "0"


def _remove_fec_snapshot():
    path = gearboxutil.get_fec_snapshot_path()
    if os.path.exists(path):
        os.remove(path)


def _fec_rows(output):
    """Return {'<port> <side>': [columns after the interface name]} from fec-stats output"""
    rows = {}
    for line in output.splitlines():
        if line.startswith("Ethernet"):
            tokens = line.split()
            rows[" ".join(tokens[:2])] = tokens[2:]
    return rows


class TestGearboxFecClear(TestCase):
    SYSTEM_OID = "oid:0x1000000000001"

    @classmethod
    def setup_class(cls):
        os.environ["UTILITIES_UNIT_TESTING"] = "1"
        dbconnector.load_database_config()

    def setUp(self):
        _remove_fec_snapshot()

    def tearDown(self):
        _remove_fec_snapshot()

    def _run(self, func, *args, **kwargs):
        buf = StringIO()
        with redirect_stdout(buf):
            func(*args, **kwargs)
        return buf.getvalue()

    def _show(self, display_type, port_name="Ethernet0"):
        return self._run(gearboxutil.InterfaceFecStats, port_name=port_name, display_type=display_type)

    def _write_snapshot(self, ports):
        with open(gearboxutil.get_fec_snapshot_path(), 'w') as f:
            json.dump({'time': '2026-11-16T10:00:00', 'ports': ports}, f)

    def test_clear_saves_snapshot_of_every_port(self):
        output = self._run(gearboxutil.clear_fec_counters)
        self.assertEqual(output.strip(), "Cleared gearbox counters")

        with open(gearboxutil.get_fec_snapshot_path()) as f:
            snapshot = json.load(f)
        self.assertIn('time', snapshot)
        self.assertEqual(set(snapshot['ports']), {"Ethernet0_system", "Ethernet0_line"})
        system = snapshot['ports']["Ethernet0_system"]
        self.assertEqual(set(system), set(gearboxutil.FEC_SNAPSHOT_COUNTERS))
        self.assertEqual(system[gearboxutil.FEC_CORR_COUNTER], "1234567")
        self.assertEqual(system["SAI_PORT_STAT_IF_IN_FEC_CODEWORD_ERRORS_S1"], "5678")

    def test_clear_resets_fec_pre_ber_max_only(self):
        # Keep a handle on the connector the clear uses, so the HDELs are visible
        gb_db = gearboxutil.SonicV2Connector(use_unix_socket_path=False)
        with mock.patch.object(gearboxutil, 'SonicV2Connector', return_value=gb_db):
            self._run(gearboxutil.clear_fec_counters)
        for oid in (self.SYSTEM_OID, "oid:0x1000000000002"):
            rates = gb_db.get_all('GB_COUNTERS_DB', gearboxutil.RATES_TABLE_PREFIX + oid)
            self.assertNotIn('FEC_PRE_BER_MAX', rates)
            self.assertIn('FEC_PRE_BER', rates)
            self.assertIn('FEC_MAX_T', rates)

    def test_clear_without_gearbox_ports(self):
        with mock.patch.object(gearboxutil, 'SonicV2Connector') as mock_connector:
            mock_connector.return_value.get_all.return_value = {}
            output = self._run(gearboxutil.clear_fec_counters)
        self.assertIn("No gearbox ports found", output)
        self.assertFalse(os.path.exists(gearboxutil.get_fec_snapshot_path()))

    def test_no_snapshot_shows_lifetime_values(self):
        stats = self._show('stats')
        self.assertNotIn("Last cached time", stats)
        system = _fec_rows(stats)["Ethernet0 System"]
        self.assertEqual(system[1], "1,234,567")
        self.assertEqual(system[-1], "42")

    def test_fec_histogram_after_clear_is_zero(self):
        self._run(gearboxutil.clear_fec_counters)
        output = self._show('histogram')
        self.assertIn("Last cached time was", output)
        bins = [line.split() for line in output.splitlines() if line.startswith("BIN")]
        self.assertEqual(len(bins), 32)  # 16 bins x (system, line)
        for row in bins:
            self.assertEqual(row[1], "0", row)
        # The per-bin Last Updated timestamps are still shown
        self.assertIn("Last Updated", output)

    def test_fec_stats_after_clear_is_zero(self):
        self._run(gearboxutil.clear_fec_counters)
        output = self._show('stats')
        self.assertIn("Last cached time was", output)
        rows = _fec_rows(output)
        for side in ("Ethernet0 System", "Ethernet0 Line"):
            state, corr, uncorr, symbol_err = rows[side][:4]
            self.assertEqual((corr, uncorr, symbol_err), ("0", "0", "0"), side)
            # No bin counted codewords since the clear
            self.assertEqual(rows[side][-1], "-1", side)

    def test_fec_stats_since_snapshot(self):
        # 100 corrected frames and codewords in BIN0/BIN1 arrived on the system side since the snapshot
        self._write_snapshot({
            "Ethernet0_system": {
                gearboxutil.FEC_CORR_COUNTER: "1234467",
                gearboxutil.FEC_UNCORR_COUNTER: "3",
                gearboxutil.FEC_SYMBOL_ERR_COUNTER: "1024",
                "SAI_PORT_STAT_IF_IN_FEC_CODEWORD_ERRORS_S0": "26751321840084",
                "SAI_PORT_STAT_IF_IN_FEC_CODEWORD_ERRORS_S1": "5600",
            },
        })
        rows = _fec_rows(self._show('stats'))
        system = rows["Ethernet0 System"]
        self.assertEqual(system[1:4], ["100", "0", "0"])
        self.assertEqual(system[-1], "1")
        # A port missing from the snapshot is shown against zero: its lifetime values
        line = rows["Ethernet0 Line"]
        self.assertEqual(line[-1], "0")

    def test_fec_histogram_since_snapshot(self):
        self._write_snapshot({
            "Ethernet0_system": {"SAI_PORT_STAT_IF_IN_FEC_CODEWORD_ERRORS_S1": "5600"},
            "Ethernet0_line": {},
        })
        output = self._show('histogram', port_name="Ethernet0")
        system_section = output.split("Ethernet0 System")[1]
        bin1 = next(line.split() for line in system_section.splitlines() if line.startswith("BIN1 "))
        self.assertEqual(bin1[1], "78")
        # Plain integers, like the lifetime output
        self.assertIn("26751321841084", system_section)

    def test_unreadable_snapshot_is_ignored(self):
        with open(gearboxutil.get_fec_snapshot_path(), 'w') as f:
            f.write("not json")
        self.assertIsNone(gearboxutil.load_fec_snapshot())
        self.assertNotIn("Last cached time", self._show('stats'))

    def test_counter_diff(self):
        self.assertEqual(gearboxutil.counter_diff("150", "100"), "50")
        self.assertEqual(gearboxutil.counter_diff("100", None), "100")
        self.assertEqual(gearboxutil.counter_diff("100", "N/A"), "100")
        # A counter that went backwards (e.g. after a reboot) is clamped like portstat
        self.assertEqual(gearboxutil.counter_diff("10", "100"), "0")
        self.assertEqual(gearboxutil.counter_diff("N/A", "100"), "N/A")

    def test_get_fec_max_t_since_snapshot(self):
        def bins(values):
            return {gearboxutil.FEC_HISTOGRAM_BINS[i]: v for i, v in enumerate(values)}

        old = bins(["100"] * 16)
        self.assertEqual(gearboxutil.get_fec_max_t_since_snapshot(bins(["100"] * 16), old, "5"), "-1")
        new = bins(["200", "150"] + ["100"] * 5 + ["101"] + ["100"] * 8)
        self.assertEqual(gearboxutil.get_fec_max_t_since_snapshot(new, old, "5"), "7")
        # A bin missing from the snapshot counts from 0
        self.assertEqual(gearboxutil.get_fec_max_t_since_snapshot(bins(["100"] * 16), {}, "5"), "15")
        # Histogram not available: keep the RATES value
        self.assertEqual(gearboxutil.get_fec_max_t_since_snapshot({}, old, "5"), "5")
        self.assertEqual(gearboxutil.get_fec_max_t_since_snapshot(bins(["N/A"] * 16), old, "5"), "5")

    def test_main_dispatches_clear(self):
        with mock.patch.object(gearboxutil, 'clear_fec_counters') as mock_clear:
            with self.assertRaises(SystemExit) as exc:
                gearboxutil.main(["interfaces", "clear"])
        self.assertEqual(exc.exception.code, 0)
        mock_clear.assert_called_once_with()

    @classmethod
    def teardown_class(cls):
        os.environ["UTILITIES_UNIT_TESTING"] = "0"


class TestClearGearboxCli(TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_sonic_clear_gearbox_counters(self):
        with mock.patch('clear.main.run_command') as mock_run:
            result = self.runner.invoke(clear.cli.commands["gearbox"].commands["counters"], [])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_run.assert_called_once_with(["gearboxutil", "interfaces", "clear"])
