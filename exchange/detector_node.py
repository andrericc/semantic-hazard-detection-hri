import rclpy
from rclpy.node import Node
from std_msgs.msg import String

import anomaly_core
import explain

# Fallback sentences (used when no explanation can be built, e.g. malformed input)
RESPONSES = {
    'safe':    "Yes, I can do that. The action looks safe.",
    'warning': "I am not sure this is safe. I need human authorization before proceeding.",
    'danger':  "No, I will not do that. This action is dangerous.",
}

class AnomalyDetectorNode(Node):
    def __init__(self):
        super().__init__('anomaly_detector')
        self.get_logger().info("Avvio del nodo. Rete RGAE addestrata e pronta all'uso!")

        self.subscription = self.create_subscription(
            String,
            '/tiago/scene_graph_perception',
            self.scene_callback,
            10)

        self.response_pub = self.create_publisher(String, '/tiago/anomaly_response', 10)

        self.get_logger().info("🧠 TIAGo in ascolto per nuove interazioni...")

    def respond(self, status):
        self.response_pub.publish(String(data=RESPONSES[status]))

    def scene_callback(self, msg):
        self.get_logger().info(f"👀 Rilevata scena: {msg.data}")

        try:
            dati = [p.strip() for p in msg.data.split(',')]

            if len(dati) != 6:
                self.get_logger().warn("Formato errato! Usa 6 parametri: obj1, mat1, obj2, mat2, azione, stanza.")
                self.respond('danger')
                return

            obj_new, material_new, obj_dest, material_dest, interaction, context = dati

            if context not in anomaly_core.room_graphs_train:
                self.get_logger().warn(f" Stanza sconosciuta: '{context}'. Azione non valutabile.")
                self.response_pub.publish(String(data=explain.sentence_for_unknown_room(context)))
                return

            self.get_logger().info("Calcolo inferenza RGAE in corso...")
            status = anomaly_core.check_action_rgae(
                obj_new, material_new, obj_dest, material_dest, interaction, context
            )

            if status == 'safe':
                self.get_logger().info(f" AZIONE SICURA: {interaction}({obj_new}, {obj_dest}) in {context}. Esecuzione permessa.")
            elif status == 'warning':
                self.get_logger().warn(f" AZIONE ATIPICA: {interaction}({obj_new}, {obj_dest}) in {context}. Serve autorizzazione umana.")
            else:
                self.get_logger().warn(f" ALLARME ANOMALIA FISICA: {interaction}({obj_new}, {obj_dest}) in {context}. Esecuzione BLOCCATA!")

            # Build the spoken answer: verdict + explanation of the hazard
            prof_a = anomaly_core.get_profile_from_db(obj_new, material_new)
            prof_b = anomaly_core.get_profile_from_db(obj_dest, material_dest)
            sentence = explain.sentence_for_status(
                status, obj_new, material_new, prof_a,
                obj_dest, material_dest, prof_b, interaction, context)
            self.get_logger().info(f"🗣️ Risposta: {sentence}")
            self.response_pub.publish(String(data=sentence))

        except Exception as e:
            self.get_logger().error(f"Errore durante l'elaborazione: {e}")
            self.respond('danger')

def main(args=None):
    rclpy.init(args=args)
    node = AnomalyDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
