#ifdef WORKBENCH

[WorkbenchPluginAttribute(name: "EMB Automation Test", description: "Prefab placement automation test", wbModules: { "WorldEditor" })]
class EMB_AutomationTestPlugin : WorldEditorPlugin
{
override void Run()
{
PlacePrefabAndSave();
}

override void RunCommandline()
{
PlacePrefabAndSave();
}

void PlacePrefabAndSave()
{
WorldEditor worldEditor = Workbench.GetModule(WorldEditor);
if (!worldEditor)
{
Print("EMB ERROR: WorldEditor module not found");
return;
}

WorldEditorAPI api = worldEditor.GetApi();
if (!api)
{
Print("EMB ERROR: WorldEditorAPI not available");
return;
}

IEntitySource existing = api.FindEntityByName("EMB_Fumarole_01");

if (existing)
{
Print("EMB INFO: prefab already exists");
}
else
{
ResourceName prefab = "{A26E161EAD3E41F5}PrefabLibrary/CainLibrary/Rocks/Granite/Fumarole_01.et";

api.BeginEntityAction("EMB Place Prefab");

IEntitySource entity = api.CreateEntity(
prefab,
"EMB_Fumarole_01",
api.GetCurrentEntityLayerId(),
null,
"10 0 10",
"0 0 0"
);

api.EndEntityAction("EMB Place Prefab");

if (!entity)
{
Print("EMB FAIL: prefab creation failed");
return;
}

Print("EMB PASS: prefab created");
}

WBModuleDef module = Workbench.GetModule(WorldEditor);
if (!module)
{
Print("EMB ERROR: WBModuleDef not available");
return;
}

if (module.Save())
Print("EMB PASS: world saved");
else
Print("EMB FAIL: world save failed");
}
}

#endif
