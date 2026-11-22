// 관찰 어노테이션. 월드 오브젝트·UI 창에 붙여 안정 id·역할·행동을 선언한다 (PLAY_PROTOCOL 1장 "게임이 선언").
using UnityEngine;

namespace Qa.Play.Perception
{
    public enum QaRole { Npc, Item, Portal, Container, Enemy, Ui, Area }

    public sealed class QaTag : MonoBehaviour
    {
        public string id;            // 안정 id: "npc_elder", "ui.dialog.choice.0" (GameObject.name·InstanceID 를 쓰지 않음)
        public QaRole role;
        public string label;         // 플레이어에게 보이는 이름
        public string[] actions = new string[0];
        public string[] tags = new string[0];
        public bool alwaysKnown;     // 시야 밖이어도 관찰에 포함 (미니맵·퀘스트 마커처럼 플레이어가 아는 것)
        public float radius = 0.5f, height = 1.8f;   // 시야 판정용 경계 상자

        public static string RoleName(QaRole r)
        {
            switch (r)
            {
                case QaRole.Npc: return "npc";
                case QaRole.Item: return "item";
                case QaRole.Portal: return "portal";
                case QaRole.Container: return "container";
                case QaRole.Enemy: return "enemy";
                case QaRole.Ui: return "ui";
                default: return "area";
            }
        }

        public static QaRole ParseRole(string s)
        {
            switch (s)
            {
                case "npc": return QaRole.Npc;
                case "item": return QaRole.Item;
                case "portal": return QaRole.Portal;
                case "container": return QaRole.Container;
                case "enemy": return QaRole.Enemy;
                case "ui": return QaRole.Ui;
                default: return QaRole.Area;
            }
        }
    }

    /// <summary>관찰에서 제외 (관람용 표시: 행동 로그 등).</summary>
    public sealed class QaIgnore : MonoBehaviour { }
}
