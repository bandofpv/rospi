import tf
import math
import rospy
from geometry_msgs.msg import Pose, PoseStamped, Twist, Quaternion
from mavros_msgs.msg import State, ExtendedState
from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest
from pymavlink import mavutil

# from mavros_msgs.srv import CommandTOL


class MavController:
    """
    Controller class to help interface with mavros
    """

    def __init__(self, send_rate):
        rospy.init_node("mav_control_node")

        rospy.Subscriber("mavros/state", State, self.state_callback)

        rospy.Subscriber("/mavros/local_position/pose", PoseStamped, self.pose_callback)

        rospy.Subscriber("/mavros/extended_state", ExtendedState, self.extended_state_callback)

        self.cmd_pos_pub = rospy.Publisher("/mavros/setpoint_position/local", PoseStamped, queue_size=1)
        self.cmd_vel_pub = rospy.Publisher("/mavros/setpoint_velocity/cmd_vel_unstamped", Twist, queue_size=1)

        # TODO: fix try and expect waits for services
        # try:
        #     rospy.wait_for_service("/mavros/cmd/set_mode")
        #     # rospy.wait_for_service("/mavros/cmd/takeoff")
        #     rospy.wait_for_service("/mavros/cmd/arming")
        # except rospy.ROSException:
        #     rospy.logerr("Failed to connect to services")

        self.mode_service = rospy.ServiceProxy('/mavros/set_mode', SetMode)
        self.arm_service = rospy.ServiceProxy('/mavros/cmd/arming', CommandBool)
        # self.takeoff_service = rospy.ServiceProxy('/mavros/cmd/takeoff', CommandTOL)
        # TODO: implement takeoff service to takeoff using current heading

        self.current_state = State()
        self.current_extended_state = ExtendedState()
        self.pose = Pose()
        self.timestamp = rospy.Time()
        self.pi_2 = math.pi / 2.0
        self.freq = send_rate
        self.rate = rospy.Rate(send_rate)

        # Wait for Flight Controller connection
        while not rospy.is_shutdown() and not self.current_state.connected:
            self.rate.sleep()

        rospy.loginfo("MAVROS Controller Initiated")

    def state_callback(self, data):
        self.current_state = data

    def extended_state_callback(self, data):
        self.current_extended_state = data

    def pose_callback(self, data):
        self.timestamp = data.header.stamp
        self.pose = data.pose

    def goto(self, pose):
        """
        Set the given pose as a next set point by sending a SET_POSITION_TARGET_LOCAL_NED message. The copter must be in
        OFFBOARD mode for this to work.
        """
        pose_stamped = PoseStamped()
        pose_stamped.header.stamp = self.timestamp
        pose_stamped.pose = pose

        self.cmd_pos_pub.publish(pose_stamped)

    def goto_xyz_rpy(self, x, y, z, ro, pi, ya, timeout, loop=True):
        pose = Pose()
        pose.position.x = x
        pose.position.y = y
        pose.position.z = z

        quat = tf.transformations.quaternion_from_euler(ro, pi, ya + self.pi_2)  # why +pi_2??

        pose.orientation.x = quat[0]
        pose.orientation.y = quat[1]
        pose.orientation.z = quat[2]
        pose.orientation.w = quat[3]

        if loop:
            for i in range(timeout * self.freq):
                self.goto(pose)
                self.rate.sleep()
        else:
            self.goto(pose)
            self.rate.sleep()

    def arm(self, timeout=5):
        """
        Arm the throttle
        """
        for i in range(timeout * self.freq):
            self.arm_service(True)
            if self.current_state.armed:
                rospy.loginfo("Armed")
                return True
            self.rate.sleep()

        rospy.logerr("Failed To Arm")

    def disarm(self):
        """
        Disarm the throttle
        """
        self.arm_service(False)

    def takeoff(self, height, timeout):
        """
        Arm the throttle and takeoff to a few feet
        """
        # Set to offboard mode
        # mode_resp = self.mode_service(custom_mode="OFFBOARD")

        self.arm()

        # Takeoff
        self.goto_xyz_rpy(0, 0, height, 0, 0, 0, timeout)

        # self.goto_xyz_rpy(self.pose.position.x, self.pose.position.y, height, 0, 0, 0)

        # return takeoff_resp

    def land(self):
        """
        Set mode to AUTO.LAND for immediate descent and disarm when on ground.
        """
        while True:
            self.mode_service(custom_mode="AUTO.LAND")
            if self.current_extended_state.landed_state == mavutil.mavlink.MAV_LANDED_STATE_ON_GROUND:
                break
            self.rate.sleep()

        rospy.loginfo("Changed Mode: Land")

        self.disarm()
        rospy.loginfo("Disarmed")

        # return resp

# TODO: add try and except to avoid errors

