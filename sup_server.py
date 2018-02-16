import socket
import threading
import time
import requests

GSM0480_OP_CODE_PROCESS_USS_REQ = 0x3B
GSM0480_OP_CODE_USS_REQUEST = 0x3C
SESSIONS = {}

class USSD_Session():
    def __init__(self, msg):
        self.phonenumber = msg.phonenumber
        self.service_code = msg.text.strip("*#").split("*")[0]
        self.session_id = msg.invoke_id
        self.first = True

    def __process_part(self, text, url):
        inp = text
        if self.first:
            text = ""
            self.first = False
        headers = {
            "Cache-Control" : "no-cache",
            "Postman-Token" : "3e3f3fb9-99b9-b47d-a358-618900d486c6"
        }
        data={
            "phoneNumber":self.phonenumber,
            "sessionId":self.session_id,
            "text":text,
            "input":inp,
            "serviceCode":self.service_code}
        print(data)
        r = requests.post(url,
            data=data,
            headers=headers)
        if r.status_code != 200:
            print("Something broke %d" % r.status_code)
            return "END Internal error, status code: " + str(r.status_code)
        print("Got " + r.text)
        return r.text

    def process(self, msg, url):
        self.msg = msg
        parts = msg.text.strip("*#").split("*")
        for s in parts:
            code, text = self.__process_part(s, url).split(" ", maxsplit=1)
            if code == "END":
                return msg.send_return_result(text)
        return msg.send_invoke(text)


class SupMessage():
    def __init__(self, data):
        """Takes in a bytearray containing a sup message and decodes it"""
        self.raw_data = data
        b = list(data)
        b.pop(0) # pop off the null byte at the start
        self.packet_len = b.pop(0)
        b.pop(0) # 0xEE
        b.pop(0) # 0x05
        assert b.pop(0) == 0x7f, "GPRS_GSUP_MSGT_MAP not found"
        self.message_type = b.pop(0)
        self.component_type = b.pop(0)
        self.transaction_id = b.pop(0)
        assert b.pop(0) == 0x02, "Invoke_id tag not found"
        b.pop(0) # invoke id length
        self.invoke_id = b.pop(0)
        self.opcode = None
        if b.pop(0) == 0x02:
            b.pop(0) # length
            self.opcode = b.pop(0)
        assert b.pop(0) == 0x04, "Text tag not found"
        self.text_length = b.pop(0)
        self.text = ""
        for i in range(self.text_length):
            self.text += chr(b.pop(0))

        assert b.pop(0) == 0x80, "Extension not found"
        self.bcd_length = b.pop(0)
        self.bcd = bytearray()
        for i in range(self.bcd_length):
            self.bcd.append(b.pop(0))
        self.__make_phonenumber()

    def __make_phonenumber(self):
        """Unpacks a phone number from a series of bytes
        The phone number is packed such that the number *123# would take
        the form 0x1a, 0x32, 0xfb
        """
        s = ""
        for b in self.bcd:
            s += "{:02x}".format(b)[::-1]
        s = s.replace("f", "").replace("a", "*").replace("b", "#")
        self.phonenumber = s

    def __send_message(self, msg_text, return_type):
        out = bytearray(b"\x00\x17\xee\x05\x7f")
        out.append(return_type)
        if return_type == GSM0480_OP_CODE_PROCESS_USS_REQ:
            out.append(0xa2)
        else:
            out.append(0xa1)
        out.append(self.transaction_id)
        out.append(0x02)
        out.append(0x01)
        out.append(self.invoke_id)
        if self.opcode:
            out.append(0x02)
            out.append(0x01)
            out.append(return_type)
        out.append(0x04)
        out.append(len(msg_text))
        out += bytearray(msg_text.encode())
        out.append(0x80)
        out.append(self.bcd_length)
        out += self.bcd
        out[1] = len(out) - 3
        return (out, return_type == GSM0480_OP_CODE_PROCESS_USS_REQ)

    def send_invoke(self, s):
        return self.__send_message(s, GSM0480_OP_CODE_USS_REQUEST)

    def send_return_result(self, s):
        return self.__send_message(s, GSM0480_OP_CODE_PROCESS_USS_REQ)


class SupServer(threading.Thread):
    def __init__(self, conn, url,  group=None, target=None, name=None, daemon=None):
        super().__init__(group=group, target=target, name=name, daemon=daemon)
        self.conn = conn
        self.url = url
        self.end = False

    def run(self):
        print("starting thread")
        sock = self.conn
        out = None
        while not self.end:
            try:
                data = sock.recv(1024)
            except OSError:
                print("connection dropped")
                sock.close()
                return
            if len(data) == 0:
                continue
            
            if len(data) > 1 and len(data) <= 4:
                # handle pings
                sock.sendall(data)

            elif len(data) > 10:
                print("received: " + str(data))
                msg = SupMessage(data)
                if msg.message_type == GSM0480_OP_CODE_PROCESS_USS_REQ:
                    SESSIONS[msg.invoke_id] = USSD_Session(msg)

                out, finished = SESSIONS[msg.invoke_id].process(msg, self.url)
                print("Sending: " + str(out))
                print(finished)
                
                if finished:
                    del SESSIONS[msg.invoke_id]
                sock.sendall(out)
            time.sleep(0.05)
        sock.close()

    def join(self):
        self.end = True
