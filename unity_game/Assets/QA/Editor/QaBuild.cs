// 빌드 스크립트. 명령행:
//   Unity.exe -batchmode -quit -projectPath unity_game -executeMethod Qa.EditorTools.QaBuild.BuildWindows -logFile Logs/build.log
// 에디터 메뉴: QA > Build Windows (QA server)
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Qa.EditorTools
{
    public static class QaBuild
    {
        public const string BootScene = "Assets/QA/Boot/Boot.unity";
        public const string Output = "Build/QaArena.exe";

        [MenuItem("QA/Build Windows (QA server)")]
        public static void BuildWindows()
        {
            EnsureBootScene();
            QaViewerAssets.Ensure();   // 뷰어 재질 (셰이더 포함용)

            PlayerSettings.companyName = "AI_QA";
            PlayerSettings.productName = "QaArena";
            PlayerSettings.runInBackground = true;
            PlayerSettings.visibleInBackground = true;
            PlayerSettings.forceSingleInstance = false;          // 포트별로 여러 인스턴스를 띄운다
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.defaultScreenWidth = 640;
            PlayerSettings.defaultScreenHeight = 360;
            PlayerSettings.resizableWindow = true;
            PlayerSettings.usePlayerLog = true;
            PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Standalone, ScriptingImplementation.Mono2x);
            PlayerSettings.SetManagedStrippingLevel(UnityEditor.Build.NamedBuildTarget.Standalone, ManagedStrippingLevel.Disabled);

            var opts = new BuildPlayerOptions
            {
                scenes = new[] { BootScene },
                locationPathName = Output,
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.None,
            };
            var report = BuildPipeline.BuildPlayer(opts);
            var s = report.summary;
            Debug.Log("[QaBuild] " + s.result + " → " + Path.GetFullPath(Output) + " (" + s.totalSize / (1024 * 1024) + " MB, " +
                      s.totalTime.TotalSeconds.ToString("0.0") + " s, errors " + s.totalErrors + ")");
            if (s.result != BuildResult.Succeeded && Application.isBatchMode) EditorApplication.Exit(1);
        }

        static void EnsureBootScene()
        {
            if (!File.Exists(BootScene))
            {
                var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                EditorSceneManager.SaveScene(scene, BootScene);
            }
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(BootScene, true) };
        }
    }
}
