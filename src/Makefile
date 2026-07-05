#
# Builds both directions of the Ancient Greek <-> Icelandic dictionary
#
# NOTE: build_dict.sh wipes the whole ./objects/ directory on every
# invocation, so each bundle must be installed immediately after it's built
# rather than building both and installing at the end (the second build
# would delete the first bundle's output first).

.PHONY: all install clean

DICT_DEV_KIT_OBJ_DIR = /Applications/XcodeAdditionalTools/Utilities/DictionaryDevelopmentKit
DICT_BUILD_TOOL_DIR  = $(DICT_DEV_KIT_OBJ_DIR)/bin
BUILD_DICT_XML       = $(DICT_BUILD_TOOL_DIR)/build_dict.sh

MIN_OS_VERSION   = 10.6
export MACOSX_DEPLOYMENT_TARGET=$(MIN_OS_VERSION)
DICT_BUILD_DIR   = ./objects
INSTALL_DIR      = $(HOME)/Library/Dictionaries

# gk2is: Ancient Greek headword -> Icelandic glossary + English (LSJ) reference
GK2IS_NAME = AncientGreekIcelandicDictionary
GK2IS_SRC  = GreekIcelandicDictionary

# is2gk: Icelandic headword -> Ancient Greek word(s), reverse index (no morphology)
IS2GK_NAME = IcelandicGreekDictionary
IS2GK_SRC  = IcelandicGreekDictionary

all: install

install:
	@mkdir -p "$(INSTALL_DIR)"
	@echo "Compiling AncientGreek -> Icelandic..."
	"$(BUILD_DICT_XML)" "$(GK2IS_NAME)" "$(GK2IS_SRC).xml" "$(GK2IS_SRC).css" "$(GK2IS_SRC).plist"
	rm -rf "$(INSTALL_DIR)/$(GK2IS_NAME).dictionary"
	cp -R "objects/$(GK2IS_NAME).dictionary" "$(INSTALL_DIR)/"
	@echo "Compiling Icelandic -> AncientGreek (reverse index)..."
	"$(BUILD_DICT_XML)" "$(IS2GK_NAME)" "$(IS2GK_SRC).xml" "$(GK2IS_SRC).css" "$(IS2GK_SRC).plist"
	rm -rf "$(INSTALL_DIR)/$(IS2GK_NAME).dictionary"
	cp -R "objects/$(IS2GK_NAME).dictionary" "$(INSTALL_DIR)/"
	@echo "Installed both bundles successfully! Refresh your Dictionary app Settings."

clean:
	@echo "Cleaning up build artifacts..."
	$(RM) -rf $(DICT_BUILD_DIR)
