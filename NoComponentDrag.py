#Author-Thomas Axelsson, ZXYNINE
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
import math, os, operator, time
from collections import deque

NAME = 'NoComponentDrag'
FILE_DIR = os.path.dirname(os.path.realpath(__file__))

# Import relative path to avoid namespace pollution
from .thomasa88lib import utils, events, manifest, error

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

def enable_cmd_created_handler(args: adsk.core.CommandCreatedEventArgs):
    global addin_updating_checkbox_
    # Check if we are updating the checkbox programmatically, to avoid infinite event recursion
    if addin_updating_checkbox_:
        return
    checkbox_def: adsk.core.CheckBoxControlDefinition = args.command.parentCommandDefinition.controlDefinition
    set_direct_edit_drag_enabled(checkbox_def.isChecked)

def set_direct_edit_drag_enabled(value):
    '''Sets the Fusion's "Component Drag" checkbox to the given value'''
    fusion_drag_controls_cmd_def_.controlDefinition.isChecked = value

def get_direct_edit_drag_enabled():
    '''Gets the value of Fusion's "Component Drag" checkbox'''
    return fusion_drag_controls_cmd_def_.controlDefinition.isChecked

def check_environment():
    global enable_cmd_def_, parametric_environment_
    
    is_parametric = is_parametric_mode()
    if parametric_environment_ == is_parametric:
        # Environment did not change
        return
    parametric_environment_ = is_parametric

    # Hide/show our menu command to avoid showing to Component Drag menu items
    # in direct edit mode (Our command + Fusion's command).
    enable_cmd_def_.controlDefinition.isVisible = is_parametric

    # We only need to update checkbox in parametric mode, as it will not be
    # seen in direct edit mode.
    if is_parametric and enable_cmd_def_.controlDefinition.isChecked != get_direct_edit_drag_enabled():
        # Fusion crashes if we change isChecked from (one of?) the event handlers,
        # so we put the update at the end of the event queue.
        events_manager_.delay(update_checkbox)

def update_checkbox():
    global addin_updating_checkbox_
    # Only set the checkbox value (triggering a command creation), if the
    # direct edit value has actually changed
    direct_edit_drag_ = get_direct_edit_drag_enabled()
    if enable_cmd_def_.controlDefinition.isChecked != direct_edit_drag_:
        addin_updating_checkbox_ = True
        enable_cmd_def_.controlDefinition.isChecked = direct_edit_drag_
        addin_updating_checkbox_ = False

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

def clear_ui_item(item):
    if item:
        item.deleteMe()

def run(context):
    #Expose global variables inside of function
    global app_, ui_, enable_cmd_def_, select_panel_, fusion_drag_controls_cmd_def_
    with error_catcher_:
        app_ = adsk.core.Application.get()
        ui_ = app_.userInterface

        fusion_drag_controls_cmd_def_ = ui_.commandDefinitions.itemById('FusionDragCompControlsCmd')

        # Clearing any previous enable_cmd_def
        clear_ui_item(ui_.commandDefinitions.itemById(ENABLE_CMD_ID))

        # There are multiple select panels. Pick the right one
        select_panel_ = ui_.toolbarPanelsByProductType('DesignProductType').itemById('SelectPanel')
        enabled = get_direct_edit_drag_enabled()

        # Use a Command to get a transaction when renaming
        enable_cmd_def_ = ui_.commandDefinitions.addCheckBoxDefinition(ENABLE_CMD_ID,
                                                                 f'Component Drag',
                                                                 'Enables or disables the movement of components by dragging '
                                                                  'in the canvas.\n\n'
                                                                  f'({NAME} v {manifest_["version"]})\n',
                                                                  enabled)
        events_manager_.add_handler(enable_cmd_def_.commandCreated,
                                    callback=enable_cmd_created_handler)
        # Removing the old control
        clear_ui_item(select_panel_.controls.itemById(ENABLE_CMD_ID))
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

        # Removing the old control
        clear_ui_item(select_panel_.controls.itemById(ENABLE_CMD_ID))
