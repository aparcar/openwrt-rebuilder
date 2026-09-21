"""Unit tests for command failure reporting."""

from rebuilder.core.command import CommandError, format_command, summarize_output

MAKE_OUTPUT = """\
SHELL= flock /tmp/sdk/tmp/.root-copy.flock -c 'cp -fpR /tmp/sdk/kmod-itco-wdt/. /tmp/sdk/root-x86/'
touch /tmp/sdk/staging_dir/target-x86_64_musl/root-x86/stamp/.kmod-itco-wdt_installed
boost/mpl.hpp:31:10: fatal error: 'boost/config.hpp' file not found
make[2]: [Makefile:75: compile] Error 1 (ignored)
make[1]: Leaving directory '/tmp/sdk'
make: *** [/tmp/sdk/include/toplevel.mk:226: package/boost/compile] Error 2
"""


FIRMWARE_OUTPUT = """\
 make[2] package/feeds/packages/foo/compile
    ERROR: package/feeds/packages/foo failed to build.
WARNING: Makefile 'package/feeds/luci/luci-app-bmx7/Makefile' has a dependency on 'bmx7', which does not exist
make: *** [/tmp/src/include/toplevel.mk:233: package/compile] Error 1
"""


class TestSummarizeOutput:
    """The lines picked out of a failed command's output."""

    def test_names_the_failing_openwrt_package(self):
        # OpenWrt indents its ERROR line and prints it to stdout; the stderr
        # warnings about missing optional deps are noise.
        assert summarize_output(FIRMWARE_OUTPUT) == [
            "    ERROR: package/feeds/packages/foo failed to build.",
            "make: *** [/tmp/src/include/toplevel.mk:233: package/compile] Error 1",
        ]

    def test_prefers_error_lines(self):
        summary = summarize_output(MAKE_OUTPUT)
        assert summary == [
            "boost/mpl.hpp:31:10: fatal error: 'boost/config.hpp' file not found",
            "make: *** [/tmp/sdk/include/toplevel.mk:226: package/boost/compile] Error 2",
        ]

    def test_ignores_bookkeeping_tail(self):
        # The last lines of a failed build are usually cleanup noise.
        assert "Leaving directory" not in "\n".join(summarize_output(MAKE_OUTPUT))

    def test_falls_back_to_tail_without_error_lines(self):
        summary = summarize_output("doing a thing\nand another\n")
        assert summary == ["doing a thing", "and another"]

    def test_empty_output(self):
        assert summarize_output("") == []

    def test_limits_length(self):
        output = "\n".join(f"make: *** error {i}" for i in range(100))
        assert len(summarize_output(output)) == 15
        assert summarize_output(output)[-1] == "make: *** error 99"


class TestCommandError:
    """The message a failed command produces."""

    def test_quotes_the_error_lines(self):
        err = CommandError(["make", "package/boost/compile"], 2, output=MAKE_OUTPUT)
        message = str(err)
        assert message.startswith("make package/boost/compile exited with code 2")
        assert (
            "  make: *** [/tmp/sdk/include/toplevel.mk:226: package/boost/compile] Error 2"
            in message
        )

    def test_no_dangling_colon_without_output(self):
        assert str(CommandError(["false"], 1)) == "false exited with code 1"

    def test_uses_stderr_when_that_is_all_there_is(self):
        err = CommandError(["gpg", "--verify"], 2, stderr="gpg: BAD signature\n")
        assert "gpg: BAD signature" in str(err)
        assert err.returncode == 2

    def test_header_stays_one_line(self):
        err = CommandError("echo one\necho two\n" + "x" * 500, 1)
        assert len(str(err).splitlines()) == 1
        assert str(err).endswith("[...] exited with code 1")


def test_format_command_renders_a_shell_line():
    assert format_command(["make", "-j4", "package/boost/compile"]) == (
        "make -j4 package/boost/compile"
    )
    assert format_command("make -j4") == "make -j4"
