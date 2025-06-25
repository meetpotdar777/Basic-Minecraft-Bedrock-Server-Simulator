import socket
import threading
import time
import struct # For packing and unpacking binary data
import random # For randomizing server GUID and player count simulation
import json # For potential structured messages (used for Gemini API payload)
import collections # For specialized container datatypes like deque, defaultdict
import hashlib # For hashing functions, potentially for IDs or simple integrity checks
import logging # For more structured logging output

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Using a simple requests-like function for fetch
# In a real async environment, you'd use a proper aiohttp or httpx
def _sync_fetch(url, method, headers, body):
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.URLError as e:
        logger.error(f"Fetch Error: {e.reason}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during fetch: {e}")
        return None

# --- IMPORTANT DISCLAIMER ---
# This script is an INTERMEDIATE UDP server simulation for Minecraft Bedrock Edition (MCPE).
# It responds to basic "unconnected ping" packets and handles more steps
# in the initial connection handshake, including several simulated interactive features.
#
# It includes:
# - Basic UDP socket setup.
# - Multithreading for listening without blocking.
# - Response to "unconnected ping" (0x01) with "unconnected pong" (0x1c).
# - Handling "Open Connection Request 1" (0x05) and sending "Open Connection Reply 1" (0x06).
# - Handling "Open Connection Request 2" (0x07) and sending "Open Connection Reply 2" (0x08).
# - Handling "Connected Ping" (0x00) and sending "Connected Pong" (0x03) for keep-alive.
# - Handling "Disconnection Notification" (0x19) for graceful client exit.
# - Simulated temporary player join/leave after connection attempt.
# - Basic Acknowledgment (ACK) simulation for incoming "play" data.
# - AI-driven simulated text message response using Google Gemini API.
# - Dynamic server information (name, player count simulation).
# - Basic simulated per-client session data management (tracking "connected" clients).
# - Simple server "game tick" simulation to process ongoing events.
# - Simulated "player joined" message in console for incoming connections.
# - Placeholder for sending a simplified "world update" message periodically.
# - **NEW**: Basic simulated player positions and random actions (move, interact).
# - **NEW**: Server "logs" simulated player actions and world events.
# - **NEW**: AI provides commentary on general simulated game events.
#
# This is STILL NOT a full-fledged, playable Minecraft server.
# The "half-functional" aspect refers to the simulator's internal state management and
# its responses becoming more complex and "game-aware" in a simulated context, not
# that it supports actual gameplay on the Minecraft client.
# For a "future generation" fully playable server, it would require:
# 1.  **Complete RakNet Protocol Implementation:** Handling reliable UDP, ordered packets,
#     fragmentation, acknowledgment, and robust session encryption (e.g., using Diffie-Hellman
#     key exchange and AES for data). This is extremely complex and would involve
#     implementing a significant portion of a network stack.
# 2.  **Full Minecraft Game Protocol:** Parsing and constructing hundreds of game-specific
#     packets for world data (chunks, blocks), entity synchronization, player actions
#     (movement, breaking, placing), inventory management, chat, commands, etc. This is
#     the core of Minecraft's unique gameplay and vast in scope.
# 3.  **Real-Time Game Engine:** Implementing physics, advanced AI for mobs, complex redstone,
#     multi-threaded world persistence (saving/loading chunks), and simulating precise
#     game ticks (e.g., 20 ticks per second) with synchronized updates for all players.
# 4.  **Performance Optimization:** Python's performance characteristics (e.g., Global
#     Interpreter Lock) are generally not suitable for the high demands of a real-time,
#     multiplayer game server at scale. Official servers are typically written in C++
#     for direct memory control and maximum efficiency.
#
# This simulator focuses on demonstrating basic network handshake stages and simulated
# interactive elements, giving a conceptual understanding of server responsibilities,
# not actual gameplay.
# For a real, playable Minecraft Bedrock server, please use the official
# Bedrock Dedicated Server software provided by Mojang/Microsoft.
# ----------------------------

# Configuration for the server
HOST = '0.0.0.0'  # Listen on all available network interfaces
PORT = 19133      # Changed default Minecraft Bedrock Edition (MCPE) port

# Server information for the mock response
SERVER_NAME = "Python MCPE Sim"
MOTD = "An Intermediate Python Server Simulation with AI!" # Updated MOTD
PROTOCOL_VERSION = 500 # Current Bedrock protocol version (might need updating for newer MCPE versions)
MINECRAFT_VERSION = "1.16.201" # Corresponding Minecraft version
PLAYER_COUNT = 0
MAX_PLAYERS = 20
SERVER_GUID = random.randint(0, 2**64 - 1) # Generate a random 64-bit server GUID
GAME_MODE = "Survival"
GAME_MODE_NUM = 1 # 0=Survival, 1=Creative
TICK_INTERVAL = 0.05 # 20 ticks per second (1/20 = 0.05 seconds) for simulated game loop

# RakNet magic bytes (used in various handshake packets)
RAKNET_MAGIC = b'\x00\xff\xff\x00\xfe\xfe\xfe\xfe\xfd\xfd\xfd\xfd\x12\x34\x56\x78'

# Constants for Open Connection Request/Reply 1 & 2
RAKNET_PROTOCOL_VERSION = 10 # RakNet Protocol Version (fixed for Open Connection Request/Reply 1)
PACKET_OPEN_CONNECTION_REQUEST_1 = 0x05
PACKET_OPEN_CONNECTION_REPLY_1 = 0x06
PACKET_OPEN_CONNECTION_REQUEST_2 = 0x07
PACKET_OPEN_CONNECTION_REPLY_2 = 0x08

# RakNet connected packet IDs (some important ones)
PACKET_CONNECTED_PING = 0x00 # Sent by client to keep connection alive
PACKET_CONNECTED_PONG = 0x03 # Sent by server in response to Connected Ping
PACKET_DISCONNECTION_NOTIFICATION = 0x19 # Sent when client gracefully disconnects

# RakNet internal IDs for reliable/ordered data (simplified for ACK)
PACKET_ACK = 0xC0 # Range 0xC0-0xCF for Acknowledgment
PACKET_NACK = 0xA0 # Range 0xA0-0xAF for Negative Acknowledgment

# A placeholder ID for where "play" packets (actual game data) would begin
# RakNet typically uses IDs >= 0x80 for user data (actual game data packets)
PACKET_ID_PLAY_DATA_START = 0x80

class BasicMCPE_Server:
    """
    A class to create and manage a basic UDP server that simulates listening
    for Minecraft Bedrock Edition connections and provides simplified responses.
    """
    def __init__(self, host, port, server_name, motd, protocol_version, mc_version,
                 initial_player_count, max_players, server_guid, game_mode, game_mode_num):
        self.host = host
        self.port = port
        self.server_name = server_name
        self.motd = motd
        self.protocol_version = protocol_version
        self.mc_version = mc_version
        self._player_count = initial_player_count
        self.max_players = max_players
        self.server_guid = server_guid
        self.game_mode = game_mode
        self.game_mode_num = game_mode_num

        self.server_socket = None
        self.running = False
        self.listener_thread = None
        self.player_sim_thread = None
        self.game_tick_thread = None
        self.player_count_lock = threading.Lock()
        # active_clients now stores more simulated player data:
        # {addr: {'last_active_time': time.time(), 'session_id': unique_id, 'pos': [x, y, z]}}
        self.active_clients = {}
        # Simple simulated world state (e.g., a few items/blocks at fixed locations)
        self.world_state = {
            "block_A": {"pos": [10, 64, 10], "type": "stone"},
            "tree_B": {"pos": [20, 65, 20], "type": "oak_log"},
        }
        self.simulated_world_events = collections.deque(maxlen=5) # Recent simulated events

    @property
    def player_count(self):
        with self.player_count_lock:
            return self._player_count

    @player_count.setter
    def player_count(self, value):
        with self.player_count_lock:
            self._player_count = max(0, min(value, self.max_players))

    def start(self):
        """
        Starts the UDP server, binds to the specified host and port,
         and begins listening for incoming packets in separate threads.
        """
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.settimeout(0.1)
            self.running = True
            logger.info(f"Basic Minecraft (MCPE) server simulator listening on {self.host}:{self.port} (UDP)")
            logger.info(f"Server Name: '{self.server_name}' - Max Players: {self.max_players}")
            logger.info("Press Ctrl+C in your terminal to stop the server.")

            self.listener_thread = threading.Thread(target=self._listen_for_packets)
            self.listener_thread.daemon = True
            self.listener_thread.start()

            self.player_sim_thread = threading.Thread(target=self._simulate_player_count)
            self.player_sim_thread.daemon = True
            self.player_sim_thread.start()

            self.game_tick_thread = threading.Thread(target=self._game_loop)
            self.game_tick_thread.daemon = True
            self.game_tick_thread.start()

        except OSError as e:
            logger.error(f"Error binding socket: {e}")
            logger.error("This often means the port is already in use by another application (e.g., another Minecraft server) or you don't have sufficient permissions.")
            logger.error("Try changing the port number or ensuring no other Minecraft server is running.")
            self.stop()
        except Exception as e:
            logger.error(f"An unexpected error occurred during server start: {e}")
            self.stop()

    def _listen_for_packets(self):
        """
        Internal method that runs in a separate thread to continuously listen
        for incoming UDP packets and respond to pings or connection requests.
        """
        while self.running:
            try:
                data, addr = self.server_socket.recvfrom(4096)

                if not data:
                    continue

                packet_id = data[0]

                if packet_id == 0x01: # Unconnected Ping
                    self._handle_unconnected_ping(data, addr)
                elif packet_id == PACKET_OPEN_CONNECTION_REQUEST_1:
                    self._handle_open_connection_request_1(data, addr)
                elif packet_id == PACKET_OPEN_CONNECTION_REQUEST_2:
                    self._handle_open_connection_request_2(data, addr)
                elif packet_id == PACKET_CONNECTED_PING:
                    self._handle_connected_ping(data, addr)
                elif packet_id == PACKET_DISCONNECTION_NOTIFICATION:
                    self._handle_disconnection_notification(data, addr)
                elif packet_id >= PACKET_ID_PLAY_DATA_START: # Placeholder for actual game data packets
                    self._handle_play_data_packet(data, addr, packet_id)
                    self._send_basic_ack(addr)
                else:
                    pass

            except socket.timeout:
                pass
            except Exception as e:
                if self.running:
                    logger.error(f"Error receiving/sending packet: {e}")

    def _simulate_player_count(self):
        """
        Simulates players joining and leaving the server over time.
        """
        while self.running:
            try:
                current_active = len(self.active_clients)
                if self.player_count < current_active:
                    self.player_count = current_active
                elif self.player_count > current_active and random.random() < 0.2:
                    self.player_count -= 1
                elif self.player_count < self.max_players and random.random() < 0.1:
                    self.player_count += 1

                time.sleep(random.uniform(5, 15))
            except Exception as e:
                if self.running:
                    logger.error(f"Error in player count simulation: {e}")
                break

    def _game_loop(self):
        """
        Simulates the server's main game loop, processing ticks.
        """
        tick_number = 0
        while self.running:
            start_time = time.time()
            tick_number += 1
            # print(f"[GAME TICK] Tick {tick_number}")

            # --- Simulate World Updates/Events ---
            if tick_number % 50 == 0: # Every 2.5 seconds (50 ticks * 0.05s/tick)
                # Example: Simulate a random "world event"
                event_type = random.choice(["weather_change", "mob_spawn", "resource_regen"])
                event_message = f"Simulated world event: {event_type} occurred at tick {tick_number}."
                self.simulated_world_events.append(event_message)
                logger.info(f"[WORLD] {event_message}")

                # Send general messages to all active clients (simplified)
                for client_addr in list(self.active_clients.keys()):
                    try:
                        self.server_socket.sendto(event_message.encode('utf-8'), client_addr)
                    except Exception as e:
                        logger.warning(f"Error sending world event message to {client_addr}: {e}. Removing from active clients.")
                        self.active_clients.pop(client_addr, None)
                        self.player_count -= 1

            # --- Check for inactive clients (a very simple timeout) ---
            current_time = time.time()
            inactive_threshold = 30 # seconds without a ping/packet
            clients_to_remove = []
            for addr, info in self.active_clients.items():
                if current_time - info['last_active_time'] > inactive_threshold:
                    clients_to_remove.append(addr)

            for addr in clients_to_remove:
                logger.info(f"Client {addr} timed out (no recent activity). Removing from active sessions.")
                self._simulate_player_leave(addr)

            end_time = time.time()
            elapsed = end_time - start_time
            sleep_time = TICK_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
            # else:
                # logger.warning(f"Game tick took too long: {elapsed:.4f}s (target {TICK_INTERVAL:.4f}s)")

        logger.info("Game tick loop stopped.")

    def _simulate_temporary_player_join(self, addr, client_id):
        """
        Simulates a player temporarily joining and then leaving the server.
        Assigns a starting simulated position.
        """
        initial_pos = [random.randint(-100, 100), 64, random.randint(-100, 100)] # Random spawn pos
        logger.info(f"Client {addr} (ID: {client_id}) attempted connection. Simulating temporary join at {initial_pos}.")
        with self.player_count_lock:
            self.active_clients[addr] = {
                'last_active_time': time.time(),
                'session_id': client_id,
                'pos': initial_pos # NEW: Simulated position
            }
            self.player_count = len(self.active_clients)
            logger.info(f"Current active clients: {len(self.active_clients)}")

        # Schedule a "disconnect" after a short period if client doesn't fully connect (which it won't)
        threading.Timer(random.uniform(10, 20), self._simulate_player_leave, args=[addr]).start()

    def _simulate_player_leave(self, addr):
        """
        Simulates a player leaving the server and cleans up its session.
        """
        if addr in self.active_clients:
            logger.info(f"Simulating disconnect for {addr}. Player count before: {self.player_count}")
            with self.player_count_lock:
                self.active_clients.pop(addr, None)
                self.player_count = len(self.active_clients)
            logger.info(f"Player count after: {self.player_count}")

    def _send_basic_ack(self, addr):
        """
        Sends a very basic, simplified RakNet Acknowledgment (ACK) packet.
        """
        response_packet = bytearray()
        response_packet.append(PACKET_ACK)
        response_packet.extend(RAKNET_MAGIC)
        try:
            self.server_socket.sendto(response_packet, addr)
            # logger.debug(f"Sent basic ACK to {addr}")
        except Exception as e:
            pass

    def _handle_unconnected_ping(self, data, addr):
        """
        Handles an "Unconnected Ping" packet (ID 0x01) by sending a mock
        "Unconnected Pong" packet (ID 0x1c).
        """
        try:
            client_timestamp = struct.unpack('>Q', data[1:9])[0]

            server_id_string = (
                f"MCPE;{self.server_name};{self.protocol_version};{self.mc_version};"
                f"{self.player_count};{self.max_players};{self.server_guid};{self.motd};"
                f"{self.game_mode};{self.game_mode_num};"
            )
            server_id_bytes = server_id_string.encode('utf-8')

            response_packet = bytearray()
            response_packet.append(0x1c)
            response_packet.extend(struct.pack('>Q', client_timestamp))
            response_packet.extend(struct.pack('>Q', self.server_guid))
            response_packet.extend(RAKNET_MAGIC)
            response_packet.extend(struct.pack('>H', len(server_id_bytes)))
            response_packet.extend(server_id_bytes)

            self.server_socket.sendto(response_packet, addr)
            logger.info(f"Sent Unconnected Pong to {addr} (Timestamp: {client_timestamp}, Players: {self.player_count}/{self.max_players})")

        except struct.error as e:
            logger.error(f"Error unpacking ping packet from {addr}: {e} (Packet too short or malformed?)")
        except Exception as e:
            logger.error(f"An error occurred handling ping from {addr}: {e}")

    def _handle_open_connection_request_1(self, data, addr):
        """
        Handles an "Open Connection Request 1" packet (ID 0x05) by sending a mock
        "Open Connection Reply 1" packet (ID 0x06).
        """
        try:
            if data[1:17] != RAKNET_MAGIC or data[17] != RAKNET_PROTOCOL_VERSION:
                logger.warning(f"Received malformed Open Connection Request 1 from {addr}. Magic or protocol version mismatch.")
                return

            mtu_size = struct.unpack('>H', data[18:20])[0]

            response_packet = bytearray()
            response_packet.append(PACKET_OPEN_CONNECTION_REPLY_1)
            response_packet.extend(RAKNET_MAGIC)
            response_packet.extend(struct.pack('>Q', self.server_guid))
            response_packet.extend(struct.pack('>H', mtu_size))
            response_packet.append(0x00)

            self.server_socket.sendto(response_packet, addr)
            logger.info(f"Sent Open Connection Reply 1 to {addr} (MTU: {mtu_size})")

        except struct.error as e:
            logger.error(f"Error unpacking Open Connection Request 1 from {addr}: {e} (Packet too short or malformed?)")
        except Exception as e:
            logger.error(f"An error occurred handling Open Connection Request 1 from {addr}: {e}")

    def _handle_open_connection_request_2(self, data, addr):
        """
        Handles an "Open Connection Request 2" packet (ID 0x07) by sending a mock
        "Open Connection Reply 2" packet (ID 0x08).
        """
        try:
            if data[1:17] != RAKNET_MAGIC:
                logger.warning(f"Received malformed Open Connection Request 2 from {addr}. Magic mismatch.")
                return

            server_guid_from_client = struct.unpack('>Q', data[17:25])[0]
            mtu_size_from_client = struct.unpack('>H', data[25:27])[0]
            client_id = struct.unpack('>Q', data[27:35])[0]

            response_packet = bytearray()
            response_packet.append(PACKET_OPEN_CONNECTION_REPLY_2)
            response_packet.extend(RAKNET_MAGIC)
            response_packet.extend(struct.pack('>Q', self.server_guid))

            ip_bytes = socket.inet_aton(addr[0])
            port_bytes = struct.pack('>H', addr[1])
            response_packet.extend(ip_bytes)
            response_packet.extend(port_bytes)

            response_packet.extend(struct.pack('>H', mtu_size_from_client))
            response_packet.append(0x00)

            self.server_socket.sendto(response_packet, addr)
            logger.info(f"Sent Open Connection Reply 2 to {addr} (Client ID: {client_id}, MTU: {mtu_size_from_client})")

            if addr not in self.active_clients:
                self._simulate_temporary_player_join(addr, client_id)
                logger.info(f"Simulated player {client_id} from {addr} has 'joined'.")

        except struct.error as e:
            logger.error(f"Error unpacking Open Connection Request 2 from {addr}: {e} (Packet too short or malformed?)")
        except Exception as e:
            logger.error(f"An error occurred handling Open Connection Request 2 from {addr}: {e}")

    def _handle_connected_ping(self, data, addr):
        """
        Handles a "Connected Ping" packet (ID 0x00) by sending a "Connected Pong" (ID 0x03).
        Also updates the client's last active time to prevent timeout.
        """
        try:
            client_timestamp = struct.unpack('>Q', data[1:9])[0]

            response_packet = bytearray()
            response_packet.append(PACKET_CONNECTED_PONG)
            response_packet.extend(struct.pack('>Q', client_timestamp))
            response_packet.extend(struct.pack('>Q', int(time.time() * 1000)))

            self.server_socket.sendto(response_packet, addr)
            logger.info(f"Sent Connected Pong to {addr} (Client Timestamp: {client_timestamp})")

            if addr in self.active_clients:
                self.active_clients[addr]['last_active_time'] = time.time()

        except struct.error as e:
            logger.error(f"Error unpacking Connected Ping from {addr}: {e} (Packet too short or malformed?)")
        except Exception as e:
            logger.error(f"An error occurred handling Connected Ping from {addr}: {e}")

    def _handle_disconnection_notification(self, data, addr):
        """
        Handles a "Disconnection Notification" packet (ID 0x19).
        Indicates the client is gracefully disconnecting.
        """
        logger.info(f"Received Disconnection Notification from {addr}. Client is disconnecting.")
        if addr in self.active_clients:
            self._simulate_player_leave(addr)

    def _handle_play_data_packet(self, data, addr, packet_id):
        """
        Handles incoming "play" data packets. Simulates player actions and triggers AI responses.
        """
        logger.info(f"Received 'Play' data packet (ID: 0x{packet_id:02x}) from {addr}.")
        logger.info(f"    Content preview: {data[1:min(len(data), 50)].hex()}...")

        if addr in self.active_clients:
            # Simulate player action and update position
            player_info = self.active_clients[addr]
            action_type = random.choice(["moved", "interacted with environment", "dug a block"])

            # Simulate movement (small random change)
            player_info['pos'][0] += random.randint(-2, 2)
            player_info['pos'][2] += random.randint(-2, 2)
            # Ensure Y stays reasonable
            player_info['pos'][1] = max(1, min(120, player_info['pos'][1] + random.randint(-1, 1)))

            simulated_event_message = (
                f"Simulated Player {player_info['session_id'] % 1000} ({addr[0]}) "
                f"{action_type} at [{player_info['pos'][0]}, {player_info['pos'][1]}, {player_info['pos'][2]}]."
            )
            self.simulated_world_events.append(simulated_event_message)
            logger.info(f"[PLAYER ACTION] {simulated_event_message}")

            # Trigger AI response based on the simulated event
            ai_prompt = f"A simulated Minecraft player just {action_type}. Provide a short, quirky game commentary message from the server."
            ai_response_thread = threading.Thread(
                target=self._get_ai_response_and_send,
                args=(ai_prompt, addr)
            )
            ai_response_thread.daemon = True
            ai_response_thread.start()
        else:
            logger.warning(f"Received play data from unknown client {addr}. Ignoring.")

        self._send_basic_ack(addr)

    def _get_ai_response_and_send(self, prompt_text, client_addr):
        """
        Calls the Gemini API to get a response and then sends it back to the client.
        """
        try:
            chat_history = [{"role": "user", "parts": [{"text": prompt_text}]}]
            payload = {"contents": chat_history}
            # IMPORTANT: For Canvas/Immersive, leave api_key as empty string.
            # The environment will inject the actual key at runtime.
            api_key = ""
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

            logger.info(f"Calling Gemini API for prompt: '{prompt_text}'")
            result = _sync_fetch(api_url, 'POST', {'Content-Type': 'application/json'}, json.dumps(payload).encode('utf-8'))

            ai_response_text = "AI is thinking..."
            if result and result.get('candidates') and len(result['candidates']) > 0 and \
               result['candidates'][0].get('content') and result['candidates'][0]['content'].get('parts') and \
               len(result['candidates'][0]['content']['parts']) > 0:
                ai_response_text = result['candidates'][0]['content']['parts'][0].get('text', "No text in AI response.")
            else:
                logger.warning(f"AI response structure unexpected: {result}")

            final_message = f"AI says: {ai_response_text}"
            try:
                self.server_socket.sendto(final_message.encode('utf-8'), client_addr)
                logger.info(f"Sent AI response to {client_addr}: '{final_message}'")
            except Exception as e:
                logger.error(f"Error sending AI response to {client_addr}: {e}")

        except Exception as e:
            logger.error(f"An error occurred during AI response generation: {e}")

    def stop(self):
        """
        Stops the UDP server and closes the socket.
        """
        if self.running:
            self.running = False
            logger.info("Stopping server...")
            if self.server_socket:
                self.server_socket.close()
                logger.info("Server socket closed.")
            if self.listener_thread and self.listener_thread.is_alive():
                self.listener_thread.join(timeout=5)
                if self.listener_thread.is_alive():
                    logger.warning("Listener thread did not terminate cleanly.")
            if self.player_sim_thread and self.player_sim_thread.is_alive():
                self.player_sim_thread.join(timeout=5)
                if self.player_sim_thread.is_alive():
                    logger.warning("Player simulation thread did not terminate cleanly.")
            if self.game_tick_thread and self.game_tick_thread.is_alive():
                self.game_tick_thread.join(timeout=5)
                if self.game_tick_thread.is_alive():
                    logger.warning("Game tick thread did not terminate cleanly.")
            logger.info("Server stopped.")

# Main execution block
if __name__ == "__main__":
    server = BasicMCPE_Server(
        HOST, PORT,
        SERVER_NAME, MOTD, PROTOCOL_VERSION, MINECRAFT_VERSION,
        PLAYER_COUNT, MAX_PLAYERS, SERVER_GUID, GAME_MODE, GAME_MODE_NUM
    )
    try:
        server.start()
        while server.running:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\nCtrl+C detected. Shutting down server...")
    finally:
        server.stop()
