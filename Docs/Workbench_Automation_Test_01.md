# Workbench Automation Test 01

Date: 2026-10-13

## Goal

Validate how far Arma Reforger World Editor can be automated through Workbench CLI and a World Editor plugin.

## Test project

Workbench project:
C:\WORK\PROJECTS\GAMEDEV\ARMA_REFORGER\Synthetic_Test_01\Workbench\Synthetic_Test_01

World:
Worlds/Automation_Test_01/Automation_Test_01.ent

## Results

### 01A ? Direct World Editor launch
PASS

Workbench can be launched directly with:
- -gproj
- -addonsDir
- -wbModule=WorldEditor
- -run

### 01B ? Automatic world load
PASS

A specific .ent world can be loaded with:
-load "Worlds/Automation_Test_01/Automation_Test_01.ent"

### 01C ? Custom World Editor plugin
PASS

A custom plugin placed under:
Scripts/WorkbenchGame/WorldEditor

is detected by World Editor and appears in the Plugins menu.

### 01D ? CLI plugin execution
PASS

The plugin can be executed through:
-plugin=EMB_AutomationTestPlugin

RunCommandline() executes successfully.

### 01E ? Modify world through WorldEditorAPI
PASS

The plugin successfully created an entity in the loaded world using WorldEditorAPI.

### 01F ? Save world from automation
PASS

Workbench module saving works through:

WBModuleDef module = Workbench.GetModule(WorldEditor);
module.Save();

The modified world persists after reopening.

### 01G ? Place real Arma Reforger prefab
PASS

Test prefab:

{A26E161EAD3E41F5}PrefabLibrary/CainLibrary/Rocks/Granite/Fumarole_01.et

The plugin successfully:
- created the prefab instance;
- assigned a name;
- positioned it;
- saved the world;
- preserved the object after reopening.

## Key finding

The following automation chain is confirmed:

PowerShell / Codex
? Workbench CLI
? open addon
? open world
? run World Editor plugin
? modify world through WorldEditorAPI
? save through WBModuleDef.Save()
? reopen persistent result

## Important implementation notes

- Workbench plugin scripts must be written without UTF-8 BOM in the current PowerShell workflow. ASCII was used successfully.
- The correct plugin directory is:
  Scripts/WorkbenchGame/WorldEditor
- GameWorldEditor is not the Workbench World Editor API and must not be used for this workflow.
- World changes should use WorldEditorAPI.
- Saving the current Workbench world is performed through WBModuleDef.Save().
- -forceSaveAll was not suitable for saving changes created later by the CLI plugin in this test.

## Next test

Automation Test 01H:
Mass prefab placement from external structured data.

Target input:
placements.csv

Planned fields:
name,prefab,x,y,z,yaw

Requirements:
- create multiple prefab instances;
- avoid duplicates by name;
- apply position and yaw;
- save automatically;
- remain reproducible from external input data.
