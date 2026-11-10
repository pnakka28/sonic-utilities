import click
import utilities_common.cli as clicommon
import utilities_common.multi_asic as multi_asic_util


def gearboxutil_cmd(args, namespace):
    cmd = ['gearboxutil']
    if namespace is not None:
        cmd += ['-n', str(namespace)]
    return cmd + args


@click.group(cls=clicommon.AliasedGroup)
def gearbox():
    """Show gearbox info"""
    pass

# 'phys' subcommand ("show gearbox phys")
@gearbox.group(cls=clicommon.AliasedGroup)
def phys():
    """Show external PHY information"""
    pass


# 'status' subcommand ("show gearbox phys status")
@phys.command('status')
@multi_asic_util.multi_asic_click_option_namespace
@click.pass_context
def phys_status(ctx, namespace):
    """Show gearbox phys status"""
    clicommon.run_command(gearboxutil_cmd(['phys', 'status'], namespace))

# 'interfaces' subcommand ("show gearbox interfaces")
@gearbox.group(cls=clicommon.AliasedGroup)
def interfaces():
    """Show gearbox interfaces information"""
    pass


# 'status' subcommand ("show gearbox interfaces status")
@interfaces.command('status')
@multi_asic_util.multi_asic_click_option_namespace
@click.pass_context
def interfaces_status(ctx, namespace):
    """Show gearbox interfaces status"""
    clicommon.run_command(gearboxutil_cmd(['interfaces', 'status'], namespace))


# 'fec-stats' subcommand ("show gearbox interfaces fec-stats")
@interfaces.command('fec-stats')
@click.argument('port_name', required=False)
@multi_asic_util.multi_asic_click_option_namespace
@click.pass_context
def fec_stats(ctx, port_name, namespace):
    """Show gearbox interfaces FEC statistics"""
    cmd = gearboxutil_cmd(['interfaces', 'fec-stats'], namespace)
    if port_name:
        cmd.append(port_name)
    clicommon.run_command(cmd)


# 'fec-histogram' subcommand ("show gearbox interfaces fec-histogram")
@interfaces.command('fec-histogram')
@click.argument('port_name', required=False)
@multi_asic_util.multi_asic_click_option_namespace
@click.pass_context
def fec_histogram(ctx, port_name, namespace):
    """Show gearbox interfaces FEC codeword error histogram"""
    cmd = gearboxutil_cmd(['interfaces', 'fec-histogram'], namespace)
    if port_name:
        cmd.append(port_name)
    clicommon.run_command(cmd)
