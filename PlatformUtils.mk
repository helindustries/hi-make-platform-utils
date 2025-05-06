PLATFORM_MAKEFILE_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
PLATFORM_UTILS_PRESENT := yes

# This is a chicken-and-egg problem, since we need Python for the `which` command as well
# as running make_platform_utils.py. We can assume that if someone cares about the Python
# version we use here, they will have it set up in their environment or in their Makefile
# before including this.
PYTHON ?= python
MAKE_PLATFORM_UTILS ?= $(PYTHON) "$(PLATFORM_MAKEFILE_DIR)/make_platform_utils.py"

PLATFORM := $(strip $(shell $(MAKE_PLATFORM_UTILS) --platform --print))
PLATFORM_ID := $(strip $(shell $(MAKE_PLATFORM_UTILS) --platform --lower --print))
PLATFORM_EXEC := $(strip $(shell $(MAKE_PLATFORM_UTILS) --platform-exec --print))
PLATFORM_OPEN := $(strip $(shell $(MAKE_PLATFORM_UTILS) --platform-open --print))

# Definitions that are not indented are so on purpose, as the result would be added to
# the result value of the call! For Windows and MinGW compatibility, we don't use the
# `func := foo $(1)` shorthand!
define env-path
$(strip $(shell $(MAKE_PLATFORM_UTILS) $(1:%=--in "%") --env-path --print))
endef
define platform-path
$(strip $(shell $(MAKE_PLATFORM_UTILS) $(1:%=--in "%") --platform-path --print))
endef
define shell-list
$(strip $(shell $(MAKE_PLATFORM_UTILS) $(1:%=--in "%") --shell-list --print))
endef
define lower
$(strip $(shell $(MAKE_PLATFORM_UTILS) --in $(1) --lower --print))
endef
define upper
$(strip $(shell $(MAKE_PLATFORM_UTILS) --in $(1) --upper --print))
endef
define exists
$(strip $(shell $(MAKE_PLATFORM_UTILS) --stoponerror false --in $(1) --exists --print))
endef
define latest
$(strip $(shell $(MAKE_PLATFORM_UTILS) --stoponerror false --in $(1) --glob --sort asc --last --print))
endef
define write
    $(MAKE_PLATFORM_UTILS) --in $(1) --out $(2)
endef
define append
    $(MAKE_PLATFORM_UTILS) --in $(1) --append $(2)
endef
define path-dirname
$(strip $(shell $(MAKE_PLATFORM_UTILS) --in $(1) --dirname --print))
endef
define path-basename
$(strip $(shell $(MAKE_PLATFORM_UTILS) --in $(1) --basename --print))
endef
define path-absolute
$(subst \\,/,$(subst :,\:,$(abspath $(1))))
endef

ifeq ($(strip $(PLATFORM_ID)),windows)
    RM ?= del /Q /F
    RMDIR ?= rmdir /S /Q
    LS ?= dir /B
    WHICH ?= $(PYTHON) -c "import shutil, sys; print(shutil.which(sys.argv[1]) or '')"
    COPY ?= copy /Y
    MOVE ?= move /Y
    TOUCH ?= $(MAKE_PLATFORM_UTILS) --touch
    MKDIR ?= mkdir
    FAIL ?= cmd /c exit 1
    LN ?= $(MAKE_PLATFORM_UTILS) --symlink
    SLEEP ?= timeout /T
else
    RM ?= rm -f
    RMDIR ?= rm -rf
    LS ?= ls -1 --color=never
    WHICH ?= which
    COPY ?= cp -f
    MOVE ?= mv -f
    TOUCH ?= touch
    MKDIR ?= mkdir -p
    FAIL ?= false
    LN ?= ln -sf
    SLEEP ?= sleep
endif
