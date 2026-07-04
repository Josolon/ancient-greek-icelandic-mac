#
# Safe Makefile for Ancient Greek -> Icelandic Dictionary Build
#

.PHONY: all install clean

DICT_NAME        = AncientGreekIcelandicDictionary
DICT_SRC_PATH    = GreekIcelandicDictionary.xml
DICT_CSS_PATH    = GreekIcelandicDictionary.css
DICT_PLIST_PATH  = GreekIcelandicDictionary.plist

DICT_DEV_KIT_OBJ_DIR = /Applications/XcodeAdditionalTools/Utilities/DictionaryDevelopmentKit
DICT_BUILD_TOOL_DIR  = $(DICT_DEV_KIT_OBJ_DIR)/bin

MIN_OS_VERSION   = 10.6
export MACOSX_DEPLOYMENT_TARGET=$(MIN_OS_VERSION)
DICT_BUILD_DIR   = ./objects
BUILD_DICT_XML   = $(DICT_BUILD_TOOL_DIR)/build_dict.sh

INSTALL_DIR      = $(HOME)/Library/Dictionaries

all:
	@echo "Compiling macOS Dictionary (Safe-Name Mode)..."
	"$(BUILD_DICT_XML)" "$(DICT_NAME)" $(DICT_SRC_PATH) $(DICT_CSS_PATH) $(DICT_PLIST_PATH)

install: all
	@echo "Moving bundle to $(INSTALL_DIR)..."
	mkdir -p "$(INSTALL_DIR)"
	rm -rf "$(INSTALL_DIR)/$(DICT_NAME).dictionary"
	cp -R "objects/$(DICT_NAME).dictionary" "$(INSTALL_DIR)/"
	@echo "Installed successfully! Refresh your Dictionary app Settings."

clean:
	@echo "Cleaning up build artifacts..."
	$(RM) -rf $(DICT_BUILD_DIR)
	$(RM) -rf "$(DICT_NAME).dictionary"
