
Name:    annobin
Summary: Annotate and examine compiled binary files
Version: 10.94
Release: 1%{?dist}
License: GPLv3+
# Maintainer: nickc@redhat.com
# Web Page: https://sourceware.org/annobin/
# Watermark Protocol: https://fedoraproject.org/wiki/Toolchain/Watermark

#---------------------------------------------------------------------------------

# Use "--without tests" to disable the testsuite.
%bcond_without tests

# Use "--without annocheck" to disable the installation of the annocheck program.
%bcond_without annocheck

# Use "--with debuginfod" to add support for debuginfod to be compiled into
# the annocheck program.  By default the configure script will check for
# availablilty at build time, but this might not match the run time situation.
# FIXME: Add a --without debuginfod option to forcefully disable the configure
# time check for debuginfod support.
%bcond_with debuginfod

# Use "--with clangplugin" to build the annobin plugin for Clang.
%bcond_with clangplugin

# Use "--without gccplugin" to disable the building of the annobin plugin for GCC.
%bcond_without gccplugin

# Use "--with llvmplugin" to build the annobin plugin for LLVM.
%bcond_with llvmplugin

# Set this to zero to disable the requirement for a specific version of gcc.
# This should only be needed if there is some kind of problem with the version
# checking logic or when building on RHEL-7 or earlier.
%global with_hard_gcc_version_requirement 1

%bcond_without plugin_rebuild
# Allow the building of annobin without using annobin itself.
# This is because if we are bootstrapping a new build environment we can have
# a new version of gcc installed, but without a new of annobin installed.
# (i.e. we are building the new version of annobin to go with the new version
# of gcc).  If the *old* annobin plugin is used whilst building this new
# version, the old plugin will complain that version of gcc for which it
# was built is different from the version of gcc that is now being used, and
# then it will abort.
#
# The default is to use annobin.  cf BZ 1630550.
%if %{without plugin_rebuild}
%undefine _annotated_build
%endif

#---------------------------------------------------------------------------------

%global annobin_sources annobin-%{version}.tar.xz
Source: https://nickc.fedorapeople.org/%{annobin_sources}
# For the latest sources use:  git clone git://sourceware.org/git/annobin.git

# This is where a copy of the sources will be installed.
%global annobin_source_dir %{_usrsrc}/annobin

# Insert patches here, if needed.  Eg:
# Patch01: annobin-foo.patch
# Insert patches here, if needed.
Patch01: annobin-nop.patch
Patch02: annobin-annocheck-no-debuginfod.patch

#---------------------------------------------------------------------------------

# [Stolen from gcc-python-plugin]
# GCC will only load plugins that were built against exactly that build of GCC
# We thus need to embed the exact GCC version as a requirement within the
# metadata.
#
# Define "gcc_vr", a variable to hold the VERSION-RELEASE string for the gcc
# we are being built against.
#
# Unfortunately, we can't simply run:
#   rpm -q --qf="%%{version}-%%{release}"
# to determine this, as there's no guarantee of a sane rpm database within
# the chroots created by our build system
#
# So we instead query the version from gcc's output.
#
# gcc.spec has:
#   Version: %%{gcc_version}
#   Release: %%{gcc_release}%%{?dist}
#   ...snip...
#   echo 'Red Hat %%{version}-%%{gcc_release}' > gcc/DEV-PHASE
#
# So, given this output:
#
#   $ gcc --version
#   gcc (GCC) 4.6.1 20110908 (Red Hat 4.6.1-9)
#   Copyright (C) 2011 Free Software Foundation, Inc.
#   This is free software; see the source for copying conditions.  There is NO
#   warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# we can scrape out the "4.6.1" from the version line.
#
# The following implements the above:

%global gcc_vr %(gcc --version | head -n 1 | sed -e 's|.*(Red\ Hat\ ||g' -e 's|)$||g')

# We need the major version of gcc.
%global gcc_major %(echo "%{gcc_vr}" | cut -f1 -d".")
%global gcc_next  %(v="%{gcc_major}"; echo $((++v)))

# Needed when building the srpm.
%if 0%{?gcc_major} == 0
%global gcc_major 0
%endif

# This is a gcc plugin, hence gcc is required.
%if %{with_hard_gcc_version_requirement}
# BZ 1607430 - There is an exact requirement on the major version of gcc.
Requires: (gcc >= %{gcc_major} with gcc < %{gcc_next})
%else
Requires: gcc
%endif

BuildRequires: gcc gcc-plugin-devel gcc-c++
# The documentation uses pod2man...
BuildRequires: perl perl-podlators
%if %{with clangplugin}
BuildRequires: clang clang-devel llvm llvm-devel compiler-rt gawk
%endif
%if %{with llvmplugin}
BuildRequires: clang clang-devel llvm llvm-devel compiler-rt gawk
%endif

%description
Provides a plugin for GCC that records extra information in the files
that it compiles.

Note - the plugin is automatically enabled in gcc builds via flags
provided by the redhat-rpm-macros package.

%if %{with clangplugin}
Also provides a plugin for Clang which performs a similar function.
%endif

%if %{with llvmplugin}
Also provides a plugin for LLVM which performs a similar function.
%endif

#---------------------------------------------------------------------------------
%if %{with tests}

%package tests
Summary: Test scripts and binaries for checking the behaviour and output of the annobin plugin

%description tests
Provides a means to test the generation of annotated binaries and the parsing
of the resulting files.

BuildRequires: make

%if %{with debuginfod}
BuildRequires: elfutils-debuginfod-client-devel
%endif

%endif

#---------------------------------------------------------------------------------
%if %{with annocheck}

%package annocheck
Summary: A tool for checking the security hardening status of binaries

BuildRequires: gcc elfutils elfutils-devel elfutils-libelf-devel rpm-devel binutils-devel make

%if %{with debuginfod}
BuildRequires: elfutils-debuginfod-client-devel
%endif

Requires: cpio rpm

%description annocheck
Installs the annocheck program which uses the notes generated by annobin to
check that the specified files were compiled with the correct security
hardening options.

%endif

#---------------------------------------------------------------------------------

%global ANNOBIN_GCC_PLUGIN_DIR %(gcc --print-file-name=plugin)

%{!?llvm_plugin_dir:%global  llvm_plugin_dir  %{_libdir}/llvm/plugins}
%{!?clang_plugin_dir:%global clang_plugin_dir %{_libdir}/clang/plugins}

%if %{with gccplugin}
# Information about the gcc plugin is recorded in this file.
%global aver annobin-plugin-version-info
%endif

#---------------------------------------------------------------------------------

%prep
if [ -z "%{gcc_vr}" ]; then
    echo "*** Missing gcc_vr spec file macro, cannot continue." >&2
    exit 1
fi

echo "Requires: (gcc >= %{gcc_major} and gcc < %{gcc_next})"

%autosetup -p1

# The plugin has to be configured with the same arcane configure
# scripts used by gcc.  Hence we must not allow the Fedora build
# system to regenerate any of the configure files.
touch aclocal.m4 gcc-plugin/config.h.in
touch configure */configure Makefile.in */Makefile.in
# Similarly we do not want to rebuild the documentation.
touch doc/annobin.info

#---------------------------------------------------------------------------------

%build

CONFIG_ARGS="--quiet --with-gcc-plugin-dir=%{ANNOBIN_GCC_PLUGIN_DIR}"

%if %{with debuginfod}
CONFIG_ARGS="$CONFIG_ARGS --with-debuginfod"
%else
# Note - we explicitly disable debuginfod support if it was not configured.
# This is because by default annobin's configue script will assume --with-debuginfod=auto
# and then run a build time test to see if debugingfod is available.  It
# may well be, but the build time environment may not match the run time
# environment, and the rpm will not have a Requirement on the debuginfod
# client.
CONFIG_ARGS="$CONFIG_ARGS --without-debuginfod"
%endif

%if %{with clangplugin}
CONFIG_ARGS="$CONFIG_ARGS --with-clang"
%endif

%if %{without gccplugin}
CONFIG_ARGS="$CONFIG_ARGS --without-gcc-plugin"
%endif

%if %{with llvmplugin}
CONFIG_ARGS="$CONFIG_ARGS --with-llvm"
%endif

%if %{without tests}
CONFIG_ARGS="$CONFIG_ARGS --without-tests"
%endif

%if %{without annocheck}
CONFIG_ARGS="$CONFIG_ARGS --without-annocheck"
%endif

%set_build_flags

export CFLAGS="$CFLAGS $RPM_OPT_FLAGS %build_cflags"
export LDFLAGS="$LDFLAGS %build_ldflags"

# Fedora supports AArch64's -mbranch-protection=bti, RHEL does not.
%if 0%{?fedora} != 0
export CFLAGS="$CFLAGS -DAARCH64_BRANCH_PROTECTION_SUPPORTED=1"
%endif

CFLAGS="$CFLAGS" LDFLAGS="$LDFLAGS" CXXFLAGS="$CFLAGS" %configure ${CONFIG_ARGS} || cat config.log

%ifarch %{ix86} x86_64
# FIXME: There should be a better way to do this.
export CLANG_TARGET_OPTIONS="-fcf-protection"
%endif

%make_build

#---------------------------------------------------------------------------------

%if %{with plugin_rebuild}
# Rebuild the plugin(s), this time using the plugin itself!  This
# ensures that the plugin works, and that it contains annotations
# of its own.

%if %{with gccplugin}
cp gcc-plugin/.libs/annobin.so.0.0.0 %{_tmppath}/tmp_annobin.so
make -C gcc-plugin clean
BUILD_FLAGS="-fplugin=%{_tmppath}/tmp_annobin.so"

# Disable the standard annobin plugin so that we do get conflicts.
OPTS="$(rpm --eval '%undefine _annotated_build %build_cflags %build_ldflags')"

# If building on RHEL7, enable the next option as the .attach_to_group
# assembler pseudo op is not available in the assembler.
# BUILD_FLAGS="$BUILD_FLAGS -fplugin-arg-tmp_annobin-no-attach"

make -C gcc-plugin CXXFLAGS="$OPTS $BUILD_FLAGS"
rm %{_tmppath}/tmp_annobin.so
%endif

%if %{with clangplugin}
cp clang-plugin/annobin-for-clang.so %{_tmppath}/tmp_annobin.so
make -C clang-plugin all CXXFLAGS="$OPTS $BUILD_FLAGS"
%endif

%if %{with llvmplugin}
cp llvm-plugin/annobin-for-llvm.so %{_tmppath}/tmp_annobin.so
make -C llvm-plugin all CXXFLAGS="$OPTS $BUILD_FLAGS"
%endif

%endif

#---------------------------------------------------------------------------------

# PLUGIN_INSTALL_DIR is used by the Clang and LLVM makefiles...
%install

%make_install PLUGIN_INSTALL_DIR=%{buildroot}/%{llvm_plugin_dir}

%if %{with clangplugin}
# Move the clang plugin to a seperate directory.
mkdir -p %{buildroot}/%{clang_plugin_dir}
mv %{buildroot}/%{llvm_plugin_dir}/annobin-for-clang.so %{buildroot}/%{clang_plugin_dir}
%endif

%if %{with gccplugin}
# Record the version of gcc that built this plugin.
# Note - we cannot just store %%{gcc_vr} as sometimes the gcc rpm version changes
# without the NVR being altered.  See BZ #2030671 for more discussion on this.
mkdir -p                             %{buildroot}/%{ANNOBIN_GCC_PLUGIN_DIR}
cat `gcc --print-file-name=rpmver` > %{buildroot}/%{ANNOBIN_GCC_PLUGIN_DIR}/%{aver}

# Also install a copy of the sources into the build tree.
mkdir -p                            %{buildroot}%{annobin_source_dir}
cp %{_sourcedir}/%{annobin_sources} %{buildroot}%{annobin_source_dir}/latest-annobin.tar.xz
%endif

rm -f %{buildroot}%{_infodir}/dir

#---------------------------------------------------------------------------------

%if %{with tests}
%check
# Change the following line to "make check || :" on RHEL7 or if you need to see the
# test suite logs in order to diagnose a test failure.
make -k check CLANG_TESTS="check-pre-clang-13"

if [ -f tests/test-suite.log ]; then
    cat tests/*.log
fi
%endif

#---------------------------------------------------------------------------------

%files
%license COPYING3 LICENSE
%exclude %{_datadir}/doc/annobin-plugin/COPYING3
%exclude %{_datadir}/doc/annobin-plugin/LICENSE
%doc %{_datadir}/doc/annobin-plugin/annotation.proposal.txt
%doc %{_infodir}/annobin.info.gz
%doc %{_mandir}/man1/annobin.1.gz
%exclude %{_mandir}/man1/built-by.1*
%exclude %{_mandir}/man1/check-abi.1*
%exclude %{_mandir}/man1/hardened.1*
%exclude %{_mandir}/man1/run-on-binaries-in.1*

%if %{with clangplugin}
%{clang_plugin_dir}/annobin-for-clang.so
%endif

%if %{with llvmplugin}
%{llvm_plugin_dir}/annobin-for-llvm.so
%endif

%if %{with gccplugin}
%{ANNOBIN_GCC_PLUGIN_DIR}/annobin.so
%{ANNOBIN_GCC_PLUGIN_DIR}/annobin.so.0
%{ANNOBIN_GCC_PLUGIN_DIR}/annobin.so.0.0.0
%{ANNOBIN_GCC_PLUGIN_DIR}/%{aver}
%{annobin_source_dir}/latest-annobin.tar.xz
%endif

%if %{with annocheck}
%files annocheck
%{_includedir}/libannocheck.h
%{_libdir}/libannocheck.*
%{_bindir}/annocheck
%doc %{_mandir}/man1/annocheck.1.gz
%{_libdir}/pkgconfig/libannocheck.pc
%endif

#---------------------------------------------------------------------------------

%changelog
* Wed Dec 07 2022 Nick Clifton  <nickc@redhat.com> - 10.94-1
- Rebase to 10.94.  (#2151312)
- Annocheck: Better detection of binaries which do not contain code.  (#2144533)
- Annocheck: Provide more information when a test is skipped because the file being tested was not compiled.
- Annocheck: Try harder not to run mutually exclusive tests.
- Tests: Fix future-test so that it properly handles the situation where the compiler does not support the new options.
- Libannocheck: Actually set result fields after tests are run.
- Libannocheck: Replace libannocheck_version variable with LIBANNOCHECK_VERSION define.
- Libannocheck: Remove 'Requires binutils-devel' from libannocheck.pc.
- Libannocheck: Move into separate sub-package.
- Libannocheck: Add libannocheck.pc pkgconfig file.
- Libannocheck: Add libannocheck_reinit().
- GCC Plugin: Record -ftrivial-auto-var-init and -fzero-call-used-regs.
- Annocheck: Add future tests for  -ftrivial-auto-var-init and -fzero-call-used-regs.
- Clang Plugin: Fix for building with Clang-15.  (#2125875)
- Annocheck: Add a test for the inconsistent use of -Ofast.  (#1248744)
- Plugin: Fix top level configuration support for RiscV.
- Annocheck: Improvements to the size tool.
- Annocheck: Fixes for libannocheck.h.
- Annocheck: Add automatic profile selection.
- Annocheck: Improve gap detection and reporting.
- Annocheck: Check build-id of separate debuginfo files.
- Annocheck: Add GAPS test replacing --ignore-gaps.
- Annocheck: Fix covscan detected race condition between stat() and open().
- Annocheck: Handle binaries created by Rust 1.18.  (#2094420)
- Annocheck: Add optional function name to --skip arguments.  (PR 29229)
- Annocheck: Fix handling of command line options that take arguments.  (#2086850)
- Annocheck: Do not complain about unenabled -mbranch-protection option in AArch64 binaries.  (#2078909)
- gcc-plugin: Fix typo in configure.ac.
- Add support for RISC-V.
- Annocheck: Add another special case for glibc rpms.  (#2083070)
- Annocheck: Do not complain about unenabled -mbranch-protection option in AArch64 binaries if compiled using LTO.  (#2082146)
- Annocheck: Add more glibc exceptions + check PT_TLS segments.  (#2081131)

* Thu Jul 21 2022 Florian Weimer <fweimer@redhat.com> - 10.67-3
- Rebuild to switch back to system annobin (#2108721)

* Fri Jul 15 2022 Florian Weimer <fweimer@redhat.com> - 10.67-2
- Rebuild to switch back to system annobin (#2001788)

* Fri Apr 29 2022 Nick Clifton  <nickc@redhat.com> - 10.67-1
- Rebuild against LLVM 14.  (#2064521)
- Annocheck: Do not complain about missing -mbranch-protection option in AArch64 binaries if compiled by golang.
- Annocheck: Do not complain about missing -mbranch-protection option in AArch64 binaries if compiled in LTO mode.
- gcc-plugin: Add support for CLVC_INTEGER options.

* Wed Apr 06 2022 Nick Clifton  <nickc@redhat.com> - 10.64-1
- Annocheck: Add more special cases for AArch64 glibc on RHEL-8.  (#2072082)
- llvm-plugin: Fix a thinko in the sources.
- gcc-plugin: Add remap of OPT_Wall.
- configure: Fix typo in top level configure.ac.
- Add support for building using meson+ninja.
- Annocheck: Fix test for AArch64 property notes.  (#2068657)
- gcc-plugin: Do not issue warning messages for autoconf generated source files.  (#2009958)

* Thu Mar 24 2022 Nick Clifton  <nickc@redhat.com> - 10.58-1
- Rebase to 10.58.  (#2067148)
- gcc-plugin: Do not issue warning messages for autoconf generated source files.  (#2009958)
- Annocheck: Update documentation and fix typo in annocheck.  (#2061291)
- Annocheck: Add option to enable/disable following symbolic links.
- Annocheck: Always identify Rust binaries, even if built on a host that does not know about Rust.  (#2057737)
- Spec File: Use a different method to disable the annobin plugin  (#2054571)
- Annocheck: Accept static GO binaries.  (#2053606)
- gcc-plugin: Fix libtool so that extraneous runpaths are not added to the plugin.  (#2047356)
- gcc-plugin: Use canonical_option field of save_decoded_options array. (#2047148)
- Annocheck: Add an option to disable the use of debuginfod (if available).
- Annocheck: Add more glibc special file names.
- Annocheck: Skip some tests for BPF binaries.  (#2044897)
- Annocheck: Skip property note test for GO binaries.  (#204300)
- Annocheck: Add another glibc static library symbol.  (#2043047)
- Spec File: Use gcc --print-file-name=rpmver for the gcc version info.
- GCC Plugin: Do not fail if a section cannot be attached to a group.
- Annocheck: Improve detection of kernel modules.
- GCC Plugin: Only default to link-once when using gcc-12 or later.  (#2039297)
- Annocheck: Add option to disable instrumentation test.
- GCC Plugin: Fix building with gcc-12.
- Spec file: Add requirement on cpio for annocheck.  (#2039747)
- Annocheck: Add even more glibc function names. (#2037333)
- Annocheck: ARM: Do not fail tests that rely upon annobin notes.
- Annocheck: Extend list of known glibc functions.  (#2037333)
- Annocheck: Ignore gaps that contain the _start symbol (for AArch64).  (#1995224)
- Annocheck: Ignore more glibc special binaries.  (#2037220)
- Annocheck: Do not complaining about missing stack clash notes if the compilation used LTO.  (#2034946)
- Annocheck: Add /usr/lib/ld-linux-aarch64.so.1 to the list of known glibc binaries.  (#2033255)
- Docs: Note that ENDBR is only needed as the landing pad for indirect branches/calls.  (#28705)
- Spec File: Store full	gcc version release string in plugin info file.  (#2030671)
- Annocheck: Add special case for x86_64 RHEL-7 gaps.  (#2031133)
- Annocheck: Do not complaining about missing -mstackrealign notes in LTO mode.  (#2030298)
- GCC Plugin: Do not record missing -mstackrealign in LTO mode.
- Tests: Fix gaps and stat tests to use newly built annobin plugin.  (#2028063)
- Annocheck: Ignore gaps in binaries at least partial built by golang.  (#2028583)
- Annocheck: Allow spaces in gloang symbols.  (#2028583)
- Annocheck: Initial deployment of libannocheck.  (#2028063)
- gcc-plugin: Fix bug creating empty attachments.
- Annocheck: Change MAYB result to SKIP for DT_RPATH.  (#2026300)
- Annocheck: Skip missing fortify/warning notes for ARM32.

* Tue Feb 08 2022 Nick Clifton  <nickc@redhat.com> - 10.29-3
- NVR bump in order to allow rebuilding against latest gcc.  (#2052060)

* Mon Jan 24 2022 Nick Clifton  <nickc@redhat.com> - 10.29-2
- Spec File: Add "Requires: rpm cpio" to annocheck sub-package.  (#2043474)

* Tue Nov 30 2021 Nick Clifton  <nickc@redhat.com> - 10.28-1
- gcc-plugin: Fix bug creating empty attachments.  (#2026944)
- Annocheck: Change MAYB result to SKIP for DT_RPATH.  (#2026300)

* Mon Nov 22 2021 Nick Clifton  <nickc@redhat.com> - 10.27-1
- Annocheck: Skip missing fortify/warning notes for ARM32.
- gcc-plugin: Try another fix for ppc64le section grouping.  (#2023437)
- gcc-plugin: Revert 10.22 change.  (#2023437)
- Annocheck: Add exception for /usr/sbin/ldconfig.  (#2022973)

* Mon Nov 08 2021 Nick Clifton  <nickc@redhat.com> - 10.23-1
- Annocheck: Add a test for unicode characters in identifiers.  (#2017363)
- gcc-plugin: Default to link-order grouping for PPC64LE.  (#2016458)

* Wed Oct 27 2021 Nick Clifton  <nickc@redhat.com> - 10.21-3
- annocheck: Disable LTO test when checking ldconfig (attempt 3).  (#2017039)

* Tue Oct 26 2021 Nick Clifton  <nickc@redhat.com> - 10.21-2
- annocheck: Disable LTO test when checking ldconfig (attempt 2).  (#2017039)

* Tue Oct 26 2021 Nick Clifton  <nickc@redhat.com> - 10.21-1
- annocheck: Disable LTO test when checking ldconfig.  (#2017039)

* Mon Oct 25 2021 Nick Clifton  <nickc@redhat.com> - 10.20-1
- annocheck: Add more glibc function names.  (#2017039)
- gcc-plugin: Fix attaching the .text section to the .text.group section.
- Complain about DT_RPATH for Fedora binaries.
- Better reporting of problems in object files.  (#2013708)
- Add a requirement on llvm-libs for clang and llvm plugins.  (#2014573)
- Fix configuring annocheck without gcc-plugin.
- Annocheck: Better reporting of debuginfod problems.
- Tests: Fix bugs in debuginfod test.

* Mon Oct 18 2021 Nick Clifton  <nickc@redhat.com> - 10.15-2
- Exclude man pages for uninstalled scripts.  (#2013565)

* Wed Oct 13 2021 Nick Clifton  <nickc@redhat.com> - 10.15-1
- Annocheck: Add tests based upon recent bug fixes.
- Annocheck: Another tweak to glibc detection code.

* Mon Oct 11 2021 Nick Clifton  <nickc@redhat.com> - 10.13-1
- Annocheck: Fix memory corruptions when using --debug-path and when a corrupt note is found.  (#20011438)
- Annocheck: Fix MAYB results for mixed GO/C files.
- Annocheck: Move some messages from VERBOSE to VERBOSE2.
- Annocheck: Scan zero-length tool notes.  (#2011818)

* Wed Oct 06 2021 Nick Clifton  <nickc@redhat.com> - 10.11-1
- Annocheck: Fix covscan detected flaws.  (#201129)
- plugins: Add more required build options.  (#2011163)

* Tue Oct 05 2021 Nick Clifton  <nickc@redhat.com> - 10.10-1
- Annocheck: Fix cf-prot test to fail if the CET notes are missing.  (#2010671)
- Annocheck: Skip gaps in the .plt section.  (#2010675)
- Plugins: Add -g option when building LLVM and Clang. (#2010675)

* Mon Oct 04 2021 Nick Clifton  <nickc@redhat.com> - 10.09-1
- Annocheck: Add more cases of glibc startup functions.  (#1981410)
- Annocheck: Fix covscan detected problems.
- Annocheck: Add --profile=el8.
- gcc-plugin: Conditionalize generation of branch protection note.
- Annocheck: Ignore gaps containing NOP instructions.

* Wed Sep 29 2021 Nick Clifton <nickc@redhat.com> - 10.06-1
- Rebase to 10.06.  (#2002351)
- GCC Plugin: Fix detection of running inside the LTO compiler.  (#2004917)
- Annocheck: Do not insist on the DT_AARCH64_PAC_PLT flag being present in AArch64 binaries.
- Annocheck: With gaps at the start/end of the .text section, check for special symbols before displaying a MAYB result.
- Annocheck: Do not set CFLAGS/LDFLAGS when building.  Take from environment instead.
- Annocheck: Fix exit code when tests PASS.
- Documentation: Add node for each hardening test.
- Documentation: Install online.
- Annocheck: Annote FAIL and MAYB results with URL to documentation
- Annocheck: Add --no-urls and --provide-urls options
- Annocheck: Add --help-<tool> option.
- Annocheck: Fix fuzzing detected failures.
- Annocheck: Add --profile option.
- Docs: Document --profile option and rpminspect.yaml.
- Annocheck: Skip GO/CET checks.  Fix fuzzing detected failures.
- LLVM Plugin: Automatically choose the correct tests to run, based upon the version of Clang installed. (#1997444)
- Annocheck: Fix memory corruption.  (#1996963)
- Annocheck: Fix conditionalization of AArch64's PAC+BTI detection.
- Annocheck: Add linker generated function for ppc64le exceptions.  (#1981410)
- LLVM Plugin: Allow checks to be selected from the command line.
- Annocheck: Examine DW_AT_producer for -flto.    
- Annocheck: Conditionalize detection of AArch64's PAC+BTI protection.
- Annocheck: Add linker generated function for s390x exceptions.  (#1981410)
- Annocheck: Generate MAYB results for gaps in notes covering the .text section.  (#1991943)
- Annocheck: Close DWARF file descriptors once the debug info is no longer needed.  (#1981410)
- LLVM Plugin: Update to build with Clang v13.  (Thanks to: Tom Stellard <tstellar@redhat.com>)
- Annocheck: Fix memory corruption.  (#1988715)
- Annocheck: Skip certain tests for kernel modules.
- Annocheck: Detect a missing CET note.  (#1991931)
- Annocheck: Do not report future fails for AArch64 notes.
- Annocheck: Warn about multiple --debug-file, --debug-rpm and --debug-dir options.
- Annocheck: Process files in command line order.  (#1988714)
- Annocheck: Reverse AArch64 PAC+BTI check, ie fail if they are enabled.  (#1984995)
- Annocheck: Add another test exceptions.
- Annocheck: Add some more test exceptions.
- Tests: Skip glibc-notes test if the assembler does not support --generate-missing-build-notes.  (#1978573)
- Tests: Skip objcopy test if objcopy does not support --merge-notes.
- Annocheck: Fix spelling mistake in -mstack-realign failure message.  (#1977349)
- gcc-plugin: Do not record global versions of stack protection settings in LTO mode, if not set.  (#1958954)
- Annocheck: Remove limit on number of input files.
- clang/llvm plugins: Build with correct security options.
- Annocheck: Better detection of GO compiler version.
- Annocheck: Better support for symbolic links.
- Annocheck: In verbose mode, report the reason for skipping specific tests.  (#1969584)
- Annocheck: Improve detection of shared libraries.  (#1958954)

* Mon May 17 2021 Nick Clifton <nickc@redhat.com> - 9.72-1
- Rebase to 9.72.  (#1960299)
- annocheck: Accept 0 as a valid number for gcc minor versions and release numbers.
- gcc-plugin: Add support for ARM and RISCV targets.
- timing: do not initialise the clock if the timing tool is disabled.
- gcc-plugin: Replace ICE messsages with verbose messages.
- Fix the testsuite so that it can be run in parallel.
- Annocheck: WARN if the annobin plugin was built for a newer version of the compiler than the one on which it was run.  (#1950657)
- Annocheck: Improve detection of missing GNU-stack support.
- Correct a package rename (bug #1949570)
- Require docs subpackage by the other ones because of a license
- Build-requiring perl-interpreter is enough
- Fix bz1949570
- Fix anomolies reported by covscan.
- Move documentation into a sub-package.

* Wed Mar 17 2021 Nick Clifton <nickc@redhat.com> - 9.65-1
- gcc-plugin: Use a fixed filename when running in LTO mode.

* Wed Mar 03 2021 Nick Clifton <nickc@redhat.com> - 9.64-1
- Annocheck: Fix detection of special function names.  (#1934189)
- Annocheck: FAIL the deliberate use of -fno-stack-protector, but add some exceptions for glibc.  (#1923439)
- Annocheck: Add colour to some messages.  Skip the deliberate use of -fno-stack-protector.  (#1923439)
- Annocheck: Fix some problems with tests for missing notes.
- Add some GO tests to annocheck.
- Add a future fail for the presence of RPATH in the dynamic tags.
- Add the ability to disable the warning message about -D_FORTIFY_SOURCE being missing.
- Workaround for elflint problems with PPC compiled files.  (#1880634)
- Fix bogus AArch64 test failures.
- Improved testing by annocheck.  Add fixed format message mode.
- Fix inconsistency reporting -fcf-protection and -fstack-clash-protection results.
- Add support for -D_FORTIFY_SOURCE=3.
- annocheck: When a binary is produced both by GAS and GCC, select GAS as the real producer.  (#1906171)
- annocheck: Improve test for LTO compiled binaries that do not have -Wall annotations.  (#1906171)

* Wed Dec 09 2020 Nick Clifton <nickc@redhat.com> - 9.50-1
- annocheck: Mark a missining -D_FORTIFY_SOURCE as a FAIL.

* Tue Dec 08 2020 Nick Clifton <nickc@redhat.com> - 9.49-1
- annocheck: Fix notes analyzer to accept empty PPC64 notes.
- gcc plugin: Tweak generation of end symbols for PPC64 when LTO is active.  (#1898075)(#1904479)
- gcc plugin: Add support for GCC 11's cl_vars array.

* Mon Nov 30 2020 Nick Clifton <nickc@redhat.com> - 9.46-1
- Annocheck: Support enabling/disabling future fails.
- GCC plugin: Always record global notes for the .text.startup,
  .text.exit, .text.hot and .text.cold sections.
- Clang plugin: Add -lLLVM to the build command line.
- Annocheck: Improve reporting of missing -D_FORTIFY_SOURCE option.  (#1898075)
- Annocheck: Improve reporting of missing LTO option.
- Add detecting of gimple compiled binaries.
- Add --without-gcc-plugin option.
- Annocheck: Fix bug parsing DW_AT_producer.
- Add test of .note.gnu.property section for PowerPC.
- Add test of objcopy's ability to merge notes.
- Record the -flto setting and produce a soft warning if it is absent.
- Suppress warnings about _D_GLIBCXX_ASSERTIONS if the source code is known to be something other than C++.

* Wed Oct 21 2020 Nick Clifton <nickc@redhat.com> - 9.35-3
- NVR bump to allow building on ELN sidetag.

* Tue Oct 13 2020 Nick Clifton <nickc@redhat.com> - 9.35-2
- Correct the directory chosen for 32-bit LLVM and Clang plugins.  (#1884951)
- Allow the use of the SHF_LINK_ORDER section flag to discard unused notes.  (Experimental).
- gcc-plugin: Fix test for empty PowerPC sections.  (#1880634)

* Thu Sep 10 2020 Nick Clifton <nickc@redhat.com> - 9.32-1
- annocheck: Add tests for the AArch64 BTI and PAC security features.  (#1862478)
- gcc plugin: Use a 4 byte offset for PowerPC start symbols, so that they do not break disassemblies.
- gcc plugin: Correct the detection of 32-bit x86 builds.  (#1876197)

* Tue Sep 08 2020 Nick Clifton <nickc@redhat.com> - 9.29-1
- gcc plugin: Detect any attempt to access the global_options array.
- gcc plugin: Do not complain about missing pre-processor options when examining a preprocessed input file.  (#1862718)
- Use more robust checks for AArch64 options.
- Detect CLANG compiled assembler that is missing IBT support.
- Improved target pointer size discovery.
- Add support for installing clang and llvm plugins.
- Temporary suppression of aarch64 pointer size check.  (#1860549)

* Wed Jul 01 2020 Nick Clifton <nickc@redhat.com> - 9.23-1
- Annocheck: Do not skip tests of the short-enums notes.  (#1743635)

* Thu Apr 23 2020 Nick Clifton <nickc@redhat.com> - 9.21-1
- Annobin: Fall back on using the flags if the option cannot be found in cl_options.  (#1817659)
- Annocheck: Detect Fortran compiled programs.  (#1824393)

* Mon Apr 06 2020 Nick Clifton <nickc@redhat.com> - 9.19-1
- Annobin: If option name mismatch occurs, seach for the real option.  (#1817452)
- Annocheck: Fix a division by zero error when parsing GO binaries.  (#1818863)
- Annobin: Fix access to the -flto and -fsanitize flags.
- Annobin: Use offsets stored in gcc's cl_option structure to access the global_options array, thus removing the need to check for changes in the size of this structure.
- Rename gcc plugin directory to gcc-plugin.
- Stop annocheck from complaining about missing options when the binary has been built in a mixed environment.
- Improve builtby tool.
- Stop annocheck complaining about missing notes when the binary is not compiled by either gcc or clang.
- Skip the check of the ENTRY instruction for binaries not compiled by gcc or clang.  (#1809656)
- Fix infinite loop hangup in annocheck.
- Disable debuginfod support by default.
- Improve parsing of .comment section.
- Fix clang plugin to use hidden symbols.
- Add ability to build clang plugin (disabled by default).
- Annocheck: Fix error printing out the version number.
- Annobin: Add checks of the exact location of the examined switches.
- Annobin: Note when stack clash notes are generated.  (#1803173, #1828797)
- Annocheck: Handle multiple builder IDs in the .comment section.
- Add configure option to suppress building annocheck.
- Fix debuginfod test.
- Correct the build requirement for building with debuginfod support.
- Add debuginfod support.
- Add clang plugin (experimental).
- Have annocheck ignore notes with an end address of 0.
- Improve checking of gcc versions.

* Fri Nov 15 2019 Nick Clifton <nickc@redhat.com> - 8.90-1
- Do not skip positive results.

* Tue Nov 12 2019 Nick Clifton <nickc@redhat.com> - 8.89-2
- Bump NVR to allow rebuild after tweaking gating tests.

* Tue Nov 12 2019 Nick Clifton <nickc@redhat.com> - 8.89-1
- Update to version 8.89.  (#1766631)
- Generate a WARN result for code compiled with instrumentation enabled.  (#1753918)
- Replace address checks with dladdr1.
- Use libabigail like checking to ensure variable address consistency.
- Skip generation of global notes for hot/cold sections.
- Generate FAIL results if -Wall or -Wformat-security are missing.
- If notes cannot be found in the executable look for them in the debuginfo file, if available.
- Generate a FAIL if notes are missing from the executable/debuginfo file.
- Record and report the setting of the AArcht64 specific -mbranch-protection option.
- Improve detection of GO binaries.
- Add gcc version information to annobin notes.
- Do not complain about missing FORTIFY_SOURCE and GLIBCXX_ASSERTIONS in LTO compilations.  (#1743635)

* Tue Aug 06 2019 Nick Clifton <nickc@redhat.com> - 8.78-1
- Fix a memory allocation error in the annobin plugin.  (#1737306)

* Mon Aug 05 2019 Nick Clifton <nickc@redhat.com> - 8.77-2
- NVR bump to allow rebuilding against latest gcc.

* Mon Jun 24 2019 Nick Clifton <nickc@redhat.com> - 8.77-1
- Another attempt at fixing the detection and reporting of missing -D_FORTIFY_SOURCE options.  (#1703500)

* Thu Jun 13 2019 Nick Clifton <nickc@redhat.com> - 8.76-2
- Release bump in order to allow rebuild against latest version of gcc in RHEL-8 buildroot.  (#1720179)

* Tue Jun 04 2019 Nick Clifton <nickc@redhat.com> - 8.76-1
- Report a missing -D_FORTIFY_SOUCRE option if -D_GLIBCXX_ASSERTIONS was detected.  (#1703500)
- Do not report problems with -fstack-protection if the binary was not built by gcc or clang.  (#1703788)    
- Add tests of clang command line options recorded in the DW_AT_producer attribute.

* Fri May 10 2019 Nick Clifton <nickc@redhat.com> - 8.73-2
- Release bump in order to allow rebuild against latest version of gcc in RHEL-8 buildroot.  (#1657912)

* Wed Apr 24 2019 Nick Clifton <nickc@redhat.com> - 8.73-1
- Fix test for an executable stack segment.  (#1700924)

* Thu Feb 28 2019 Nick Clifton <nickc@redhat.com> - 8.71-1
- Annobin: Suppress more calls to free() which are triggering memory checker errors.  (#1684148)

* Fri Feb 01 2019 Nick Clifton <nickc@redhat.com> - 8.70-1
- Add section flag matching ability to section size tool.

* Thu Jan 31 2019 Fedora Release Engineering <releng@fedoraproject.org> - 8.69-7
- Rebuilt for https://fedoraproject.org/wiki/Fedora_30_Mass_Rebuild

* Tue Jan 29 2019 Björn Esser <besser82@fedoraproject.org> - 8.69-6
- Use 'with' for rich dependency on gcc

* Tue Jan 29 2019 Björn Esser <besser82@fedoraproject.org> - 8.69-5
- Really fix rhbz#1607430.

* Mon Jan 28 2019 Björn Esser <besser82@fedoraproject.org> - 8.69-4
- Rebuilt with annotations enabled

* Mon Jan 28 2019 Björn Esser <besser82@fedoraproject.org> - 8.69-3
- Fix rpm query for gcc version.

* Mon Jan 28 2019 Nick Clifton <nickc@redhat.com> - 8.69-2
- Add an exact requirement on the major version of gcc. (#1607430)

* Thu Jan 24 2019 Nick Clifton <nickc@redhat.com> - 8.69-1
- Annobin: Add support for .text.startup and .text.exit sections generated by gcc 9.
- Annocheck: Add a note displaying tool.

* Wed Jan 23 2019 Nick Clifton <nickc@redhat.com> - 8.68-1
- Annocheck: Skip checks for -D_FORTIFY_SOURCE and -D_GLIBCXX_ASSERTIONS if there is no compiler generated code in the binary.

* Mon Jan 21 2019 Björn Esser <besser82@fedoraproject.org> - 8.67-3
- Rebuilt with annotations enabled

* Mon Jan 21 2019 Björn Esser <besser82@fedoraproject.org> - 8.67-2
- Rebuilt for GCC 9

* Thu Jan 17 2019 Nick Clifton <nickc@redhat.com> - 8.67-1
- Annocheck: Only skip specific checks for specific symbols.  (#1666823)
- Annobin: Record the setting of the -fomit-frame-pointer option.  (#1657912)

* Wed Jan 02 2019 Nick Clifton <nickc@redhat.com> - 8.66-1
- Annocheck: Do not ignore -Og when checking to see if an optimization level has been set.  (#1624162)

* Tue Dec 11 2018 Nick Clifton <nickc@redhat.com> - 8.65-1
- Annobin: Fix handling of multiple .text.unlikely sections.

* Fri Nov 30 2018 Nick Clifton <nickc@redhat.com> - 8.64-1
- Annocheck: Skip gaps in PPC64 executables covered by start_bcax_ symbols.  (#1630564)

* Mon Nov 26 2018 Nick Clifton <nickc@redhat.com> - 8.63-1
- Annocheck: Disable ENDBR test for shared libraries.  (#1652925)

* Mon Nov 26 2018 Nick Clifton <nickc@redhat.com> - 8.62-1
- Annocheck: Add test for ENDBR instruction at entry address of x86/x86_64 executables.  (#1652925)

* Tue Nov 20 2018 David Cantrell <dcantrell@redhat.com> - 8.61-2
- Adjust how the gcc_vr macro is set.

* Mon Nov 19 2018 Nick Clifton <nickc@redhat.com> - 8.61-1
- Fix building with gcc version 4.

* Tue Nov 13 2018 Nick Clifton <nickc@redhat.com> - 8.60-1
- Skip -Wl,-z,now and -Wl,-z,relro checks for non-gcc produced binaries.  (#1624421)

* Mon Nov 05 2018 Nick Clifton <nickc@redhat.com> - 8.59-1
- Ensure GNU Property notes are 8-byte aligned in x86_64 binaries.  (#1645817)

* Thu Oct 18 2018 Nick Clifton <nickc@redhat.com> - 8.58-1
- Skip PPC64 linker stubs created in the middle of text sections (again). (#1630640)

* Thu Oct 18 2018 Nick Clifton <nickc@redhat.com> - 8.57-1
- Suppress free of invalid pointer. (#1638371)

* Thu Oct 18 2018 Nick Clifton <nickc@redhat.com> - 8.56-1
- Skip PPC64 linker stubs created in the middle of text sections. (#1630640)

* Tue Oct 16 2018 Nick Clifton <nickc@redhat.com> - 8.55-1
- Reset the (PPC64) section start symbol to 0 if its section is empty.  (#1638251)

* Thu Oct 11 2018 Nick Clifton <nickc@redhat.com> - 8.53-1
- Also skip virtual thinks created by G++.  (#1630619)

* Wed Oct 10 2018 Nick Clifton <nickc@redhat.com> - 8.52-1
- Use uppercase for all fail/mayb/pass results.  (#1637706)

* Wed Oct 10 2018 Nick Clifton <nickc@redhat.com> - 8.51-1
- Generate notes for unlikely sections.  (#1630620)

* Mon Oct 08 2018 Nick Clifton <nickc@redhat.com> - 8.50-1
- Fix edge case computing section names for end symbols.  (#1637039)

* Mon Oct 08 2018 Nick Clifton <nickc@redhat.com> - 8.49-1
- Skip dynamic checks for binaries without a dynamic segment.  (#1636606)

* Fri Oct 05 2018 Nick Clifton <nickc@redhat.com> - 8.48-1
- Delay generating attach_to_group directives until the end of the compilation.  (#1636265)

* Mon Oct 01 2018 Nick Clifton <nickc@redhat.com> - 8.47-1
- Fix bug introduced in previous delta which would trigger a seg-fault when scanning for gaps.

* Mon Oct 01 2018 Nick Clifton <nickc@redhat.com> - 8.46-1
- Annobin:   Fix section name selection for startup sections.
- Annocheck: Improve gap skipping heuristics.   (#1630574)

* Mon Oct 01 2018 Nick Clifton <nickc@redhat.com> - 8.45-1
- Fix function section support (again).   (#1630574)

* Fri Sep 28 2018 Nick Clifton <nickc@redhat.com> - 8.44-1
- Skip compiler option checks for non-GNU producers.  (#1633749)

* Wed Sep 26 2018 Nick Clifton <nickc@redhat.com> - 8.43-1
- Fix function section support (again).   (#1630574)

* Tue Sep 25 2018 Nick Clifton <nickc@redhat.com> - 8.42-1
- Ignore ppc64le notes where start = end + 2.  (#1632259)

* Tue Sep 25 2018 Nick Clifton <nickc@redhat.com> - 8.41-1
- Make annocheck ignore symbols suffixed with ".end".  (#1639618)

* Mon Sep 24 2018 Nick Clifton <nickc@redhat.com> - 8.40-1
- Reinstate building annobin with annobin enabled.  (#1630550)

* Mon Sep 24 2018 Nick Clifton <nickc@redhat.com> - 8.39-2
- Fix gating test.  (#1625683)

* Fri Sep 21 2018 Nick Clifton <nickc@redhat.com> - 8.39-1
- Tweak tests.

* Fri Sep 21 2018 Nick Clifton <nickc@redhat.com> - 8.38-1
- Generate notes and groups for .text.hot and .text.unlikely sections.
- When -ffunction-sections is active, put notes for startup sections into .text.startup.foo rather than .text.foo.
- Similarly put exit section notes into .text.exit.foo.  (#1630574)
- Change annocheck's maybe result for GNU Property note being missing into a PASS if it is not needed and a FAIL if it is needed.

* Wed Sep 19 2018 Nick Clifton <nickc@redhat.com> - 8.37-1
- Make the --skip-* options skip all messages about the specified test.
- Add gating tests.   (#1625683)

* Tue Sep 18 2018 Nick Clifton <nickc@redhat.com> - 8.36-1
- Improve error message when an ET_EXEC binary is detected.

* Mon Sep 17 2018 Nick Clifton <nickc@redhat.com> - 8.35-1
- Skip failures for PIC vs PIE.  (#1629698)

* Mon Sep 17 2018 Nick Clifton <nickc@redhat.com> - 8.34-1
- Ensure 4 byte alignment of note sub-sections.  (#1629671)

* Wed Sep 12 2018 Nick Clifton <nickc@redhat.com> - 8.33-1
- Add timing tool to report on speed of the checks.
- Add check for conflicting use of the -fshort-enum option.
- Add check of the GNU Property notes.
- Skip check for -O2 if compiled with -Og.  (#1624162)

* Mon Sep 03 2018 Nick Clifton <nickc@redhat.com> - 8.32-1
- Add test for ET_EXEC binaries.  (#1625627)
- Document --report-unknown option.

* Thu Aug 30 2018 Nick Clifton <nickc@redhat.com> - 8.31-1
- Fix bug in hardened tool which would skip gcc compiled files if the notes were too small.
- Fix bugs in section-size tool.
- Fix bug in built-by tool.

* Wed Aug 29 2018 Nick Clifton <nickc@redhat.com> - 8.30-1
- Generate notes for comdat sections. (#1619267)

* Thu Aug 23 2018 Nick Clifton <nickc@redhat.com> - 8.29-1
- Add more names to the gap skip list. (#1619267)

* Thu Aug 23 2018 Nick Clifton <nickc@redhat.com> - 8.28-1
- Skip gaps covered by _x86.get_pc_thunk and _savegpr symbols. (#1619267)
- Merge ranges where one is wholly covered by another.

* Wed Aug 22 2018 Nick Clifton <nickc@redhat.com> - 8.27-1
- Skip gaps at the end of functions. (#1619267)

* Tue Aug 21 2018 Nick Clifton <nickc@redhat.com> - 8.26-1
- Fix thinko in ppc64 gap detection code. (#1619267)

* Mon Aug 20 2018 Nick Clifton <nickc@redhat.com> - 8.25-1
- Skip gaps at the end of the .text section in ppc64 binaries. (#1619267)

* Fri Aug 17 2018 Nick Clifton <nickc@redhat.com> - 8.24-1
- Skip checks in stack_chk_local_fail.c.  (#1618660)
- Treat gaps as FAIL results rather than MAYBE.
- Skip checks in __stack_chk_local_fail.
- Reduce version check to gcc major version number only.  Skip compiler option checks if binary not built with gcc.  (#1603089)
- Fix bug in annobin plugin.  Add --section-size=NAME option to annocheck.

* Thu Aug 02 2018 Nick Clifton <nickc@redhat.com> - 8.20-1
- Correct name of man page for run-on-binaries-in script.  (#1611155)

* Mon Jul 30 2018 Florian Weimer <fweimer@redhat.com> - 8.19-3
- Rebuild with fixed binutils

* Sat Jul 28 2018 Troy Dawson <tdawson@redhat.com> - 8.19-2
- Rebuild for gcc 8.2.1

* Wed Jul 25 2018 Nick Clifton <nickc@redhat.com> - 8.19-1
- Allow $ORIGN to be at the start of entries in DT_RPATH and DT_RUNPATH.

* Mon Jul 23 2018 Nick Clifton <nickc@redhat.com> - 8.18-1
- Add support for big endian targets.

* Mon Jul 23 2018 Nick Clifton <nickc@redhat.com> - 8.17-1
- Count passes and failures on a per-component basis and report gaps.

* Fri Jul 20 2018 Nick Clifton <nickc@redhat.com> - 8.16-1
- Use our own copy of the targetm.asm_out.function_section() function.  (#159861 comment#17)

* Fri Jul 20 2018 Nick Clifton <nickc@redhat.com> - 8.15-1
- Generate grouped note section name all the time.  (#159861 comment#16)

* Thu Jul 19 2018 Nick Clifton <nickc@redhat.com> - 8.14-1
- Fix section conflict problem.  (#1603071)

* Wed Jul 18 2018 Nick Clifton <nickc@redhat.com> - 8.13-1
- Fix for building with gcc version 4.
- Fix symbol placement in functions with local assembler.

* Tue Jul 17 2018 Nick Clifton <nickc@redhat.com> - 8.12-1
- Fix assertions in rnage checking code.  Add detection of -U options.

* Tue Jul 17 2018 Nick Clifton <nickc@redhat.com> - 8.11-1
- Handle function sections properly.  Handle .text.startup and .text.unlikely sections.  Improve gap detection and reporting.  (#1601055)

* Thu Jul 12 2018 Nick Clifton <nickc@redhat.com> - 8.10-1
- Fix construction of absolute versions of --dwarf-dir and --debug-rpm options.

* Tue Jul 10 2018 Nick Clifton <nickc@redhat.com> - 8.9-1
- Fix buffer overrun when very long symbol names are encountered.

* Tue Jul 10 2018 Nick Clifton <nickc@redhat.com> - 8.8-1
- Do not force the generation of function notes when -ffunction-sections is active.  (#1598961)

* Mon Jul 09 2018 Nick Clifton <nickc@redhat.com> - 8.7-1
- Skip the .annobin_ prfix when reporting symbols.  (#1599315)

* Mon Jul 09 2018 Nick Clifton <nickc@redhat.com> - 8.6-1
- Use the assembler (c++ mangled) version of function names when switching sections.  (#1598579)

* Mon Jul 09 2018 Nick Clifton <nickc@redhat.com> - 8.5-1
- Do not call function_section.  (#1598961)

* Fri Jul 06 2018 Nick Clifton <nickc@redhat.com> - 8.4-1
- Ignore cross-section gaps.  (#1598551)

* Thu Jul 05 2018 Nick Clifton <nickc@redhat.com> - 8.3-1
- Do not skip empty range notes in object files.  (#1598361)

* Mon Jul 02 2018 Nick Clifton <nickc@redhat.com> - 8.2-1
- Create the start symbol at the start of the function and the end symbol at the end.  (#1596823)

* Mon Jul 02 2018 Nick Clifton <nickc@redhat.com> - 8.1-1
- Fix --debug-rpm when used inside a directory.

* Thu Jun 28 2018 Nick Clifton <nickc@redhat.com> - 8.0-1
- Use a prefix for all annobin generated symbols, and make them hidden.
- Only generate weak symbol definitions for linkonce sections.

* Wed Jun 27 2018 Nick Clifton <nickc@redhat.com> - 7.1-1
- Skip some checks for relocatable object files, and dynamic objects.
- Stop bogus complaints about stackrealignment not being enabled.

* Mon Jun 25 2018 Nick Clifton <nickc@redhat.com> - 7.0-1
- Add -debug-rpm= option to annocheck.
- Only use a 2 byte offset for the initial symbol on PowerPC.

* Fri Jun 22 2018 Nick Clifton <nickc@redhat.com> - 6.6-1
- Use --dwarf-path when looking for build-id based debuginfo files.

* Fri Jun 22 2018 Nick Clifton <nickc@redhat.com> - 6.5-1
- Fix premature closing of dwarf handle.

* Fri Jun 22 2018 Nick Clifton <nickc@redhat.com> - 6.4-1
- Fix scoping bug computing the name of a separate debuginfo file.

* Tue Jun 19 2018 Nick Clifton <nickc@redhat.com> - 6.3-1
- Fix file descriptor leak.

* Tue Jun 19 2018 Nick Clifton <nickc@redhat.com> - 6.2-1
- Add command line options to annocheck to disable individual tests.

* Fri Jun 08 2018 Nick Clifton <nickc@redhat.com> - 6.1-1
- Remove C99-ism from annocheck sources.

* Wed Jun 06 2018 Nick Clifton <nickc@redhat.com> - 6.0-1
- Add the annocheck program.

* Fri Jun 01 2018 Nick Clifton <nickc@redhat.com> - 5.11-1
- Do not use the SHF_GNU_BUILD_NOTE section flag.

* Thu May 31 2018 Nick Clifton <nickc@redhat.com> - 5.10-1
- Remove .sh extension from shell scripts.

* Wed May 30 2018 Nick Clifton <nickc@redhat.com> - 5.9-1
- Record the setting of the -mstackrealign option for i686 binaries.

* Mon May 14 2018 Nick Clifton <nickc@redhat.com> - 5.8-1
- Hide the annobin start of file symbol.

* Tue May 08 2018 Nick Clifton <nickc@redhat.com> - 5.7-1
- Fix script bug in hardended.sh.  (Thanks to: Stefan Sørensen <stefan.sorensen@spectralink.com>)

* Thu May 03 2018 Nick Clifton <nickc@redhat.com> - 5.6-3
- Version number bump so that the plugin can be rebuilt with the latest version of GCC.

* Mon Apr 30 2018 Nick Clifton <nickc@redhat.com> - 5.6-2
- Rebuild the plugin with the newly created plugin enabled.  (#1573082)

* Mon Apr 30 2018 Nick Clifton <nickc@redhat.com> - 5.6-1
- Skip the isa_flags check in the ABI test because the crt[in].o files are compiled with different flags from the test files.

* Fri Apr 20 2018 Nick Clifton <nickc@redhat.com> - 5.3-1
- Add manual pages for annobin and the scripts.

* Tue Apr 03 2018 Nick Clifton <nickc@redhat.com> - 5.2-1
- Do not record a stack protection setting of -1.  (#1563141)

* Tue Mar 20 2018 Nick Clifton <nickc@redhat.com> - 5.1-1
- Do not complain about a dwarf_version value of -1.  (#1557511)

* Thu Mar 15 2018 Nick Clifton <nickc@redhat.com> - 5.0-1
- Bias file start symbols by 2 in order to avoid them confused with function symbols.  (#1554332)
- Version jump is to sync the version number with the annobin plugins internal version number.

* Mon Mar 12 2018 Nick Clifton <nickc@redhat.com> - 3.6-1
- Add --ignore-gaps option to check-abi.sh script.
- Use this option in the abi-test check.
- Tweak hardening test to skip pic and stack protection checks.

* Tue Mar 06 2018 Nick Clifton <nickc@redhat.com> - 3.5-1
- Handle functions with specific assembler names.  (#1552018)

* Fri Feb 23 2018 Nick Clifton <nickc@redhat.com> - 3.4-2
- Add an explicit requirement on the version of gcc used to built the plugin.  (#1547260)

* Fri Feb 09 2018 Nick Clifton <nickc@redhat.com> - 3.4-1
- Change type and size of symbols to STT_NOTYPE/0 so that they do not confuse GDB.  (#1539664)
- Add run-on-binaries-in.sh script to allow the other scripts to be run over a repository.

* Wed Feb 07 2018 Fedora Release Engineering <releng@fedoraproject.org> - 3.3-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_28_Mass_Rebuild

* Tue Jan 30 2018 Nick Clifton <nickc@redhat.com> - 3.3-1
- Rebase on 3.3 release, which adds support for recording -mcet and -fcf-protection.

* Mon Jan 29 2018 Florian Weimer <fweimer@redhat.com> - 3.2-3
- Rebuild for GCC 8

* Fri Jan 26 2018 Nick Clifton <nickc@redhat.com> - 3.2-2
- Fix the installation of the annobin.info file.

* Fri Jan 26 2018 Nick Clifton <nickc@redhat.com> - 3.2-1
- Rebase on 3.2 release, which now contains documentation!

* Fri Jan 26 2018 Richard W.M. Jones <rjones@redhat.com> - 3.1-3
- Rebuild against GCC 7.3.1.

* Tue Jan 16 2018 Nick Clifton <nickc@redhat.com> - 3.1-2
- Add --with-gcc-plugin-dir option to the configure command line.

* Thu Jan 04 2018 Nick Clifton <nickc@redhat.com> - 3.1-1
- Rebase on version 3.1 sources.

* Mon Dec 11 2017 Nick Clifton <nickc@redhat.com> - 2.5.1-5
- Do not generate notes when there is no output file.  (#1523875)

* Fri Dec 08 2017 Nick Clifton <nickc@redhat.com> - 2.5.1-4
- Invent an input filename when reading from a pipe.  (#1523401)

* Thu Nov 30 2017 Florian Weimer <fweimer@redhat.com> - 2.5.1-3
- Use DECL_ASSEMBLER_NAME for symbol references (#1519165)

* Tue Oct 03 2017 Igor Gnatenko <ignatenkobrain@fedoraproject.org> - 2.5.1-2
- Cleanups in spec

* Tue Sep 26 2017 Nick Clifton <nickc@redhat.com> - 2.5.1-1
- Touch the auto-generated files in order to stop them from being regenerated.

* Tue Sep 26 2017 Nick Clifton <nickc@redhat.com> - 2.5-2
- Stop the plugin complaining about compiler datestamp mismatches.

* Thu Sep 21 2017 Nick Clifton <nickc@redhat.com> - 2.4-1
- Tweak tests so that they will run on older machines.

* Thu Sep 21 2017 Nick Clifton <nickc@redhat.com> - 2.3-1
- Add annobin-tests subpackage containing some preliminary tests.
- Remove link-time test for unsuported targets.

* Wed Aug 02 2017 Fedora Release Engineering <releng@fedoraproject.org> - 2.0-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Binutils_Mass_Rebuild

* Mon Jul 31 2017 Florian Weimer <fweimer@redhat.com> - 2.0-2
- Rebuild with binutils fix for ppc64le (#1475636)

* Wed Jun 28 2017 Nick Clifton <nickc@redhat.com> - 2.0-1
- Fixes for problems reported by the package submission review:
   * Add %%license entry to %%file section.
   * Update License and BuildRequires tags.
   * Add Requires tag.
   * Remove %%clean.
   * Add %%check.
   * Clean up the %%changelog.
- Update to use version 2 of the specification and sources.

* Thu May 11 2017 Nick Clifton <nickc@redhat.com> - 1.0-1
- Initial submission.
