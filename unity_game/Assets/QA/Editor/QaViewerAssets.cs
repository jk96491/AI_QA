// 뷰어 재질 템플릿 생성: Assets/Presentation/Resources/QaView/{Lit,Glow,Fade}.mat
// Resources 에 있는 재질이 쓰는 셰이더(및 _EMISSION 변형)는 빌드에 포함된다 → 빌드에서도 Shader.Find 실패 없음.
// 에디터를 열 때와 빌드 전에 자동으로 확인한다.
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Qa.EditorTools
{
    [InitializeOnLoad]
    public static class QaViewerAssets
    {
        const string Dir = "Assets/Presentation/Resources/QaView";

        static QaViewerAssets()
        {
            EditorApplication.delayCall += () => { if (!Application.isBatchMode) Ensure(); };
        }

        [MenuItem("QA/Viewer/Rebuild Materials", false, 20)]
        public static void Ensure()
        {
            if (!Directory.Exists(Dir)) Directory.CreateDirectory(Dir);
            bool changed = false;
            changed |= Make("Lit", "Standard", m => { });
            changed |= Make("Glow", "Standard", m =>
            {
                m.EnableKeyword("_EMISSION");
                m.SetColor("_EmissionColor", Color.white);
                m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            });
            changed |= Make("Fade", "Sprites/Default", m => { m.color = new Color(1, 1, 1, 0.5f); });
            if (changed) AssetDatabase.SaveAssets();
        }

        static bool Make(string name, string shader, System.Action<Material> setup)
        {
            var path = Dir + "/" + name + ".mat";
            if (AssetDatabase.LoadAssetAtPath<Material>(path) != null) return false;
            var s = Shader.Find(shader);
            if (s == null)
            {
                Debug.LogError("[QA] 셰이더 없음: " + shader);
                return false;
            }
            var m = new Material(s) { name = name };
            setup(m);
            AssetDatabase.CreateAsset(m, path);
            return true;
        }
    }
}
