// 플레이 모드 UI 자산 준비 (빌드 전 자동):
//  1) TMP Essential Resources 확인 (TMP Settings·기본 글꼴·셰이더) — 없으면 TextMeshPro 가 동작하지 않는다. QaTools~/import_tmp_essentials.py 로 풀어 둔다
//  2) 런타임 동적 글꼴(맑은 고딕)이 쓰는 "TextMeshPro/Mobile/Distance Field" 셰이더를 빌드에 포함시키기 위한 재질
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Qa.EditorTools
{
    public static class QaPlayAssets
    {
        const string TmpSettings = "Assets/TextMesh Pro/Resources/TMP Settings.asset";
        const string Dir = "Assets/Presentation/Resources/QaPlay";
        const string SdfMat = Dir + "/TmpMobileSdf.mat";

        [MenuItem("QA/Play/Ensure UI Assets", false, 30)]
        public static bool Ensure()
        {
            if (AssetDatabase.LoadAssetAtPath<Object>(TmpSettings) == null)
            {
                // ImportPackage 는 비동기라 batchmode 빌드 안에서 끝나지 않는다 → 도구로 한 번 풀어 둔다
                Debug.LogError("[QaBuild] TMP Essential Resources 없음 — python unity_game/QaTools~/import_tmp_essentials.py 실행 후 다시 빌드");
                return false;
            }
            if (AssetDatabase.LoadAssetAtPath<Material>(SdfMat) == null)
            {
                var s = Shader.Find("TextMeshPro/Mobile/Distance Field");
                if (s == null)
                {
                    Debug.LogError("[QaBuild] 셰이더 TextMeshPro/Mobile/Distance Field 없음");
                    return false;
                }
                if (!Directory.Exists(Dir)) Directory.CreateDirectory(Dir);
                AssetDatabase.CreateAsset(new Material(s) { name = "TmpMobileSdf" }, SdfMat);
                AssetDatabase.SaveAssets();
            }
            return true;
        }
    }
}
