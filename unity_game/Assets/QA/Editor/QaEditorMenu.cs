// 에디터 메뉴: QA > Play Mode Server (켜기/끄기, 포트). 설정은 EditorPrefs (이 PC 사용자별).
using Qa.Boot;
using UnityEditor;
using UnityEngine;

namespace Qa.EditorTools
{
    public static class QaEditorMenu
    {
        const string MenuToggle = "QA/Play Mode Server/Enabled";

        [MenuItem(MenuToggle, false, 1)]
        static void Toggle()
        {
            bool on = !EditorPrefs.GetBool(QaBoot.EditorPrefEnabled, false);
            EditorPrefs.SetBool(QaBoot.EditorPrefEnabled, on);
            Debug.Log("[QA] Play Mode Server " + (on ? "켜짐" : "꺼짐") + " (포트 " + EditorPrefs.GetInt(QaBoot.EditorPrefPort, QaBoot.DefaultEditorPort) + ")");
        }

        [MenuItem(MenuToggle, true)]
        static bool ToggleValidate()
        {
            Menu.SetChecked(MenuToggle, EditorPrefs.GetBool(QaBoot.EditorPrefEnabled, false));
            return !EditorApplication.isPlaying;
        }

        [MenuItem("QA/Play Mode Server/Port...", false, 2)]
        static void Port() => EditorWindow.GetWindow<QaPortWindow>(true, "QA Server Port").ShowUtility();
    }

    public sealed class QaPortWindow : EditorWindow
    {
        int _port;

        void OnEnable()
        {
            _port = EditorPrefs.GetInt(QaBoot.EditorPrefPort, QaBoot.DefaultEditorPort);
            minSize = maxSize = new Vector2(320, 90);
        }

        void OnGUI()
        {
            EditorGUILayout.LabelField("Play 모드에서 QA 서버가 열 포트", EditorStyles.boldLabel);
            _port = EditorGUILayout.IntField("Port", _port);
            EditorGUILayout.HelpBox("빌드 인스턴스와 같은 포트를 쓰면 충돌합니다.", MessageType.None);
            if (GUILayout.Button("저장"))
            {
                EditorPrefs.SetInt(QaBoot.EditorPrefPort, Mathf.Clamp(_port, 1, 65535));
                Close();
            }
        }
    }
}
