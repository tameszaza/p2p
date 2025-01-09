import argparse
import asyncio
import json
import os
import sys

from aiortc import RTCPeerConnection, RTCSessionDescription

# We'll use a single data channel for both chat & file transfer
CHANNEL_LABEL = "p2p-data-channel"

async def run_offer(pc, file_to_send):
    """
    This function is run when we are in "offer" mode.
    We create an offer, print it to the console, and wait for the answer.
    """
    # Create data channel for chat & file transfer
    channel = pc.createDataChannel(CHANNEL_LABEL)
    channel.on("open", lambda: on_channel_open(channel, file_to_send))
    channel.on("message", on_message_received)

    # Create and set local (offer) SDP
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    # Print the local SDP in JSON form (user will copy this to the other peer)
    print("=== Your OFFER (copy and send to the Answer peer) ===")
    print(json.dumps({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    }))
    print("======================================================")

    # Wait here for user to input the ANSWER from the other peer
    answer_str = input("Paste the ANSWER from the other peer and press Enter:\n").strip()
    try:
        answer_json = json.loads(answer_str)
        answer = RTCSessionDescription(sdp=answer_json["sdp"], type=answer_json["type"])
        await pc.setRemoteDescription(answer)
    except Exception as e:
        print(f"Failed to parse answer: {e}")
        return

    # Keep the program alive to allow chat/file transfer
    await hold_connection()

async def run_answer(pc, file_to_send):
    """
    This function is run when we are in "answer" mode.
    We wait for the user to paste the offer, then produce an answer for them to paste back.
    """
    # Wait for the user to input the OFFER
    offer_str = input("Paste the OFFER from the other peer and press Enter:\n").strip()

    try:
        offer_json = json.loads(offer_str)
        offer = RTCSessionDescription(sdp=offer_json["sdp"], type=offer_json["type"])
        await pc.setRemoteDescription(offer)
    except Exception as e:
        print(f"Failed to parse offer: {e}")
        return

    # Once remote description is set, create data channel handler
    @pc.on("datachannel")
    def on_datachannel(channel):
        print(f"DataChannel created by remote with label {channel.label}")
        channel.on("message", on_message_received)
        channel.on("open", lambda: on_channel_open(channel, file_to_send))

    # Create and set local (answer) SDP
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # Print the local SDP in JSON form (user will copy this to the other peer)
    print("=== Your ANSWER (copy and send to the Offer peer) ===")
    print(json.dumps({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    }))
    print("=====================================================")

    # Keep the program alive to allow chat/file transfer
    await hold_connection()

def on_channel_open(channel, file_to_send):
    """
    Called when data channel is open. We can either send a text prompt or send a file if specified.
    """
    print("Data channel is open! You can start chatting or send a file.")

    # If a file is specified, automatically start file transfer
    if file_to_send and os.path.isfile(file_to_send):
        asyncio.ensure_future(send_file(channel, file_to_send))
    else:
        # Allow user to type messages if no file is specified
        asyncio.ensure_future(chat_prompt(channel))

async def chat_prompt(channel):
    """
    Continuously prompt the user to input chat messages and send them.
    """
    while True:
        message = input("You: ").strip()
        if message.lower() == "bye":
            print("Ending chat. Goodbye!")
            break
        channel.send(message)

async def send_file(channel, file_path):
    """
    Send a file across the data channel in small chunks.
    """
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    print(f"Sending file '{file_name}' ({file_size} bytes)...")

    # Let the remote side know we're sending a file and its name
    meta_info = json.dumps({"file_name": file_name, "file_size": file_size, "type": "file_meta"})
    channel.send(meta_info)

    # Send the file in chunks
    chunk_size = 16000
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            channel.send(chunk)
    print(f"File '{file_name}' sent successfully!")

def on_message_received(message):
    """
    Called when a message is received. We'll handle both text and file chunks.
    """
    print(f"DEBUG: Message received: {message}")
    if isinstance(message, bytes):
        handle_binary_message(message)
    else:
        try:
            data = json.loads(message)
            if data.get("type") == "file_meta":
                file_name = data["file_name"]
                file_size = data["file_size"]
                print(f"Incoming file: {file_name} ({file_size} bytes)")
                open_file_receiver(file_name, file_size)
            else:
                print("Peer:", data)
        except:
            print("Peer:", message)


incoming_files = {}

def open_file_receiver(file_name, file_size):
    """
    Prepare to receive a file by opening it in a local file.
    """
    incoming_files[file_name] = {
        "file_name": file_name,
        "file_size": file_size,
        "received_bytes": 0,
        "handle": open("received_" + file_name, "wb")
    }
    print(f"Receiving file will be saved as 'received_{file_name}'")

def handle_binary_message(message):
    """
    Called when we receive a binary message (file chunk).
    """
    if len(incoming_files) == 1:
        file_info = next(iter(incoming_files.values()))
        file_info["handle"].write(message)
        file_info["received_bytes"] += len(message)

        if file_info["received_bytes"] >= file_info["file_size"]:
            file_info["handle"].close()
            print(f"File '{file_info['file_name']}' received successfully!")
            incoming_files.pop(file_info["file_name"])
    else:
        print("Warning: Received file chunk but no metadata or multiple files in progress!")

async def hold_connection():
    """
    Keep the program running so the user can chat and send/receive files.
    Press Ctrl+C to exit.
    """
    print("Connection established. Press Ctrl+C to stop.")
    while True:
        await asyncio.sleep(1)

def main():
    parser = argparse.ArgumentParser(description="Simple P2P WebRTC with chat & file transfer")
    parser.add_argument("--role", choices=["offer", "answer"], required=True, help="Role of this peer")
    parser.add_argument("--file", help="Path to a file you want to send (optional)", default=None)
    args = parser.parse_args()

    pc = RTCPeerConnection()

    loop = asyncio.get_event_loop()

    try:
        if args.role == "offer":
            loop.run_until_complete(run_offer(pc, args.file))
        else:
            loop.run_until_complete(run_answer(pc, args.file))
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(pc.close())

if __name__ == "__main__":
    main()
