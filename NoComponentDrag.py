#Author-Thomas Axelsson 
#Issue fix by ZXYNINE
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

# Force modules to be fresh during development
import importlib
importlib.reload(thomasa88lib.utils)
importlib.reload(thomasa88lib.events)
importlib.reload(thomasa88lib.manifest)
importlib.reload(thomasa88lib.error)

ENABLE_CMD_ID = 'thomasa88_NoComponentDrag_Enable'
DIRECT_EDIT_DRAG_CMD_ID = 'FusionDragCompControlsCmd'

app_ = None
ui_ = None
error_catcher_ = thomasa88lib.error.ErrorCatcher()
events_manager_ = thomasa88lib.events.EventsManager(error_catcher_)
manifest_ = thomasa88lib.manifest.read()

select_panel_ = None
enable_cmd_def_ = None
parametric_environment_ = True
addin_updating_checkbox_ = False
fusion_drag_controls_cmd_def_ = None

checking_environment_queued_ = False

def command_starting_handler(args: adsk.core.ApplicationCommandEventArgs):
    # Should we block?
    if parametric_environment_ and args.commandId == 'FusionDragComponentsCommand' and not get_direct_edit_drag_enabled():
        args.isCanceled = True

def command_terminated_handler(args: adsk.core.ApplicationCommandEventArgs):
    # Detect if user toggles Direct Edit or enters/leaves a Base Feature
    # Undo/Redo triggers the ActivateEnvironmentCommand instead.
    # PLM360OpenAttachmentCommand, CurrentlyOpenDocumentsCommand are workarounds for DocumentActivated with Drawings bug.
    # https://forums.autodesk.com/t5/fusion-360-api-and-scripts/api-bug-application-documentactivated-event-do-not-raise/m-p/9020750
    if (args.commandId in ('ActivateEnvironmentCommand', 'PLM360OpenAttachmentCommand', 'CurrentlyOpenDocumentsCommand') or
        (args.terminationReason == adsk.core.CommandTerminationReason.CompletedTerminationReason and
         args.commandId in ('Undo', 'Redo','ConvertToPMDesignCommand', 'ConvertToDMDesignCommand',
                            'BaseFeatureActivate', 'BaseFeatureStop', 'BaseFeatureCreationCommand'))):
        check_environment()

def document_activated_handler(args: adsk.core.WorkspaceEventArgs):
    check_environment()

    # Is called three times per window switch and only two times when first starting and only once when trying to insert a derive
    # A msgbox was placed in and I noticed the insert window actually does open meaning the addon is removing it. the insert window dissapears after the return
def enable_cmd_created_handler(args: adsk.core.CommandCreatedEventArgs):
    global addin_updating_checkbox_
    # Check if we are updating the checkbox programmatically, to avoid infite event recursion
    if addin_updating_checkbox_:
        return
    checkbox_def: adsk.core.CheckBoxControlDefinition = args.command.parentCommandDefinition.controlDefinition
    set_direct_edit_drag_enabled(checkbox_def.isChecked)

def set_direct_edit_drag_enabled(value):
    fusion_drag_controls_cmd_def_.controlDefinition.isChecked = value

def get_direct_edit_drag_enabled():
    return fusion_drag_controls_cmd_def_.controlDefinition.isChecked

    # This function was found to be the source of the multiple calls of "enable_cmd_created_handler"
    # I noticed the update was being delayed but multiple sources can call check_environment leading to multiple updated being queued sequentially causing debugging to be a nightmare
    # On stopping the multiple updates from queueing issue "NoComponentDrag breaks Insert -> Derive" was solved i assume because the final update was overriding the insert window
def check_environment():
    # If a check environment is already queued then skip adding another.
    # IMPORTANT: May need to add code that removes the last placed check env and places another at the end of the queue if anything is queued in between calls of check env if errors occur
    global checking_environment_queued_
    if not checking_environment_queued_:
        return
    # Don't make a double command in the direct editing environment
    global enable_cmd_def_
    global parametric_environment_
    parametric_environment_ = is_parametric_mode()
    enable_cmd_def_.controlDefinition.isVisible = parametric_environment_
    def update():
        global addin_updating_checkbox_
        global checking_environment_queued_
        addin_updating_checkbox_ = True
        enable_cmd_def_.controlDefinition.isChecked = get_direct_edit_drag_enabled()
        addin_updating_checkbox_ = False
        checking_environment_queued_ = False
    # Fusion crashes if we changed isChecked from (one of?) the event handlers,
    # so we put the update at the end of the event queue.
    events_manager_.delay(update)
    checking_environment_queued_ = True

def is_parametric_mode():
    try:
        # UserInterface.ActiveWorkspace throws when it is called from DocumentActivatedHandler
        # during Fusion 360 start-up(?). Checking for app_.isStartupComplete does not help.
        if ui_.activeWorkspace.id == 'FusionSolidEnvironment':
            design = adsk.fusion.Design.cast(app_.activeProduct)
            if design and design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
                return True
    except:
        pass
    return False

def run(context):
    global app_
    global ui_
    global enable_cmd_def_
    global select_panel_
    global fusion_drag_controls_cmd_def_
    with error_catcher_:
        app_ = adsk.core.Application.get()
        ui_ = app_.userInterface

        fusion_drag_controls_cmd_def_ = ui_.commandDefinitions.itemById('FusionDragCompControlsCmd')

        enable_cmd_def_ = ui_.commandDefinitions.itemById(ENABLE_CMD_ID)
        if enable_cmd_def_:
            enable_cmd_def_.deleteMe()

        # There are multiple select panels. Pick the right one
        select_panel_ = ui_.toolbarPanelsByProductType('DesignProductType').itemById('SelectPanel')
        enabled = get_direct_edit_drag_enabled()

        # Use a Command to get a transaction when renaming
        enable_cmd_def_ = ui_.commandDefinitions.addCheckBoxDefinition(ENABLE_CMD_ID,
                                                                 f'Component Drag',
                                                                 'Enables or disables the movement of components by dragging '
                                                                  'in the canvas.\n\n'
                                                                  f'({NAME} v {manifest_["version"]})',
                                                                  enabled)
        events_manager_.add_handler(enable_cmd_def_.commandCreated,
                                    callback=enable_cmd_created_handler)
        old_control = select_panel_.controls.itemById(ENABLE_CMD_ID)
        if old_control:
            old_control.deleteMe()
        select_panel_.controls.addCommand(enable_cmd_def_, DIRECT_EDIT_DRAG_CMD_ID, False)

        events_manager_.add_handler(ui_.commandStarting, callback=command_starting_handler)
        events_manager_.add_handler(ui_.commandTerminated, callback=command_terminated_handler)

        # Fusion bug: DocumentActivated is not called when switching to/from Drawing.
        # https://forums.autodesk.com/t5/fusion-360-api-and-scripts/api-bug-application-documentactivated-event-do-not-raise/m-p/9020750
        events_manager_.add_handler(app_.documentActivated,
                                    callback=document_activated_handler)

        # Workspace is not ready when starting (?)
        if app_.isStartupComplete:
            check_environment()
        
        # Checking workspace type in DocumentActivated handler fails since Fusion 360 v2.0.10032
        # Put a check at the end of the event queue instead.
        events_manager_.delay(check_environment)

def stop(context):
    with error_catcher_:
        events_manager_.clean_up()

        old_control = select_panel_.controls.itemById(ENABLE_CMD_ID)
        if old_control:
            old_control.deleteMe()
