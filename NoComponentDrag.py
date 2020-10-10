#Author-Thomas Axelsson
#Description-Blocks Component Dragging in parametric mode

# This file is part of NoComponentDrag, a Fusion 360 add-in for blocking
# component drags.
#
# Copyright (c) 2020 Thomas Axelsson
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import adsk.core, adsk.fusion, adsk.cam, traceback

from collections import deque
import math
import os
import operator
import time

NAME = 'NoComponentDrag'
FILE_DIR = os.path.dirname(os.path.realpath(__file__))

# Import relative path to avoid namespace pollution
from .thomasa88lib import utils
from .thomasa88lib import events
from .thomasa88lib import manifest
from .thomasa88lib import error
from .thomasa88lib import settings

# Force modules to be fresh during development
import importlib
importlib.reload(thomasa88lib.utils)
importlib.reload(thomasa88lib.events)
importlib.reload(thomasa88lib.manifest)
importlib.reload(thomasa88lib.error)
importlib.reload(thomasa88lib.settings)

ENABLE_CMD_ID = 'thomasa88_NoComponentDrag_Enable'
SEPARATOR_ID = 'thomasa88_NoComponentDrag_SeparatorAfter'

app_ = None
ui_ = None
error_catcher_ = thomasa88lib.error.ErrorCatcher()
events_manager_ = thomasa88lib.events.EventsManager(error_catcher_)
manifest_ = thomasa88lib.manifest.read()
settings_ = thomasa88lib.settings.SettingsManager(
    { 'drag_enabled': True }
)

enable_cmd_def_ = None
right_environment_ = True

def command_starting_handler(args: adsk.core.ApplicationCommandEventArgs):
    # Should we block?
    if right_environment_ and not settings_['drag_enabled'] and args.commandId == 'FusionDragComponentsCommand':
        args.isCanceled = True

def command_terminated_handler(args: adsk.core.ApplicationCommandEventArgs):
    # Detect if user toggles Direct Edit or enters/leaves a Base Feature
    if (args.commandId in ('ConvertToPMDesignCommand', 'ConvertToDMDesignCommand', 'BaseFeatureActivate', 'BaseFeatureStop') and
        args.terminationReason == adsk.core.CommandTerminationReason.CompletedTerminationReason):
        check_environment()

def enable_cmd_created_handler(args: adsk.core.CommandCreatedEventArgs):
    checkbox_def: adsk.core.CheckBoxControlDefinition = args.command.parentCommandDefinition.controlDefinition
    if checkbox_def.isChecked:
        settings_['drag_enabled'] = True
    else:
        settings_['drag_enabled'] = False

def document_activated_handler(args: adsk.core.WorkspaceEventArgs):
    check_environment()

def check_environment():
    # Don't make a double command in the direct editing environment
    global enable_cmd_def_
    global right_environment_
    
    right_environment_ = is_parametric_mode()
    enable_cmd_def_.controlDefinition.isVisible = right_environment_

def is_parametric_mode():
    if ui_.activeWorkspace.id == 'FusionSolidEnvironment':
        design: adsk.fusion.Design = app_.activeProduct
        if design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
            return True
    return False

def run(context):
    global app_
    global ui_
    global enable_cmd_def_
    with error_catcher_:
        app_ = adsk.core.Application.get()
        ui_ = app_.userInterface

        enable_cmd_def_ = ui_.commandDefinitions.itemById(ENABLE_CMD_ID)
        if enable_cmd_def_:
            enable_cmd_def_.deleteMe()

        # Use a Command to get a transaction when renaming
        enable_cmd_def_ = ui_.commandDefinitions.addCheckBoxDefinition(ENABLE_CMD_ID,
                                                                 f'Component Drag',
                                                                 'Enables or disables the movement of components by dragging '
                                                                  'in the canvas.\n\n'
                                                                  f'({NAME} v {manifest_["version"]})',
                                                                  settings_['drag_enabled'])
        events_manager_.add_handler(enable_cmd_def_.commandCreated,
                                    callback=enable_cmd_created_handler)

        panel_id = 'SelectPanel'
        # There are multiple select panels. Pick the right one
        panel = ui_.toolbarPanelsByProductType('DesignProductType').itemById(panel_id)
        old_control = panel.controls.itemById(ENABLE_CMD_ID)
        if old_control:
            old_control.deleteMe()
        panel.controls.addCommand(enable_cmd_def_, 'SeparatorAfter_SelectionToolsDropDown', False)

        old_control = panel.controls.itemById(SEPARATOR_ID)
        if old_control:
            old_control.deleteMe()
        panel.controls.addSeparator(SEPARATOR_ID, ENABLE_CMD_ID, False)

        events_manager_.add_handler(ui_.commandStarting, callback=command_starting_handler)
        events_manager_.add_handler(ui_.commandTerminated, callback=command_terminated_handler)

        # Fusion bug: DocumentActivated is not called when switching to/from Drawing.
        # https://forums.autodesk.com/t5/fusion-360-api-and-scripts/api-bug-application-documentactivated-event-do-not-raise/m-p/9020750
        events_manager_.add_handler(app_.documentActivated,
                                    callback=document_activated_handler)

        # Workspace is not ready when starting (?)
        if app_.isStartupComplete:
            check_environment()

def stop(context):
    with error_catcher_:
        events_manager_.clean_up()

        panel_id = 'SelectPanel'
        panel = ui_.toolbarPanelsByProductType('DesignProductType').itemById(panel_id)
        old_control = panel.controls.itemById(ENABLE_CMD_ID)
        if old_control:
            old_control.deleteMe()

        old_control = panel.controls.itemById(SEPARATOR_ID)
        if old_control:
            old_control.deleteMe()
