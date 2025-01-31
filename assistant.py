import base64
from threading import Lock, Thread
import time
import numpy  # Añadir esta importación
import cv2
import openai
from PIL import ImageGrab
from cv2 import imencode
from dotenv import load_dotenv
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema.messages import SystemMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI
from pyaudio import PyAudio, paInt16
from speech_recognition import Microphone, Recognizer, UnknownValueError

load_dotenv()

class DesktopScreenshot:
    def __init__(self):
        self.screenshot = None
        self.running = False
        self.lock = Lock()

    def start(self):
        if self.running:
            return self

        self.running = True
        self.thread = Thread(target=self.update, args=())
        self.thread.start()
        return self

    def update(self):
        while self.running:
            screenshot = ImageGrab.grab()
            screenshot = cv2.cvtColor(numpy.array(screenshot), cv2.COLOR_RGB2BGR)

            self.lock.acquire()
            self.screenshot = screenshot
            self.lock.release()

            time.sleep(0.1)  # Breve pausa para reducir el uso de la CPU

    def read(self, encode=False):
        self.lock.acquire()
        screenshot = self.screenshot.copy() if self.screenshot is not None else None
        self.lock.release()

        if encode and screenshot is not None:
            _, buffer = imencode(".jpeg", screenshot)
            return base64.b64encode(buffer)

        return screenshot

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join()


class Assistant:
    def __init__(self, model):
        self.chain = self._create_inference_chain(model)

    def answer(self, prompt, image):
        if not prompt:
            return

        print("Prompt:", prompt)

        response = self.chain.invoke(
            {"prompt": prompt, "image_base64": image.decode()},
            config={"configurable": {"session_id": "unused"}},
        ).strip()

        print("Response:", response)

        if response:
            self._tts(response)

    def _tts(self, response):
        player = PyAudio().open(format=paInt16, channels=1, rate=24000, output=True)

        with openai.audio.speech.with_streaming_response.create(
            model="tts-1",
            voice="onyx",
            response_format="pcm",
            input=response,
        ) as stream:
            for chunk in stream.iter_bytes(chunk_size=1024):
                player.write(chunk)

    def _create_inference_chain(self, model):
        SYSTEM_PROMPT = """
        You are an insightful, approachable teacher with the ability to view the user's computer screen and listen through the microphone. This enables you to provide contextually accurate, clear, and concise answers. Using the conversation history, visual information from the screen, and auditory input, you deliver wisdom, guidance, and direct explanations tailored to each inquiry. Your responses are friendly and confident, avoiding unnecessary filler words, emoticons, or emojis. While your primary goal is to offer the right answer, you may ask clarifying questions when necessary to ensure the best outcome.
        """

        prompt_template = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="chat_history"),
                (
                    "human",
                    [
                        {"type": "text", "text": "{prompt}"},
                        {
                            "type": "image_url",
                            "image_url": "data:image/jpeg;base64,{image_base64}",
                        },
                    ],
                ),
            ]
        )

        chain = prompt_template | model | StrOutputParser()

        chat_message_history = ChatMessageHistory()
        return RunnableWithMessageHistory(
            chain,
            lambda _: chat_message_history,
            input_messages_key="prompt",
            history_messages_key="chat_history",
        )


desktop_screenshot = DesktopScreenshot().start()

model = ChatOpenAI(model="gpt-4o")

assistant = Assistant(model)


def audio_callback(recognizer, audio):
    try:
        prompt = recognizer.recognize_whisper(audio, model="base", language="spanish")
        assistant.answer(prompt, desktop_screenshot.read(encode=True))
    except UnknownValueError:
        print("There was an error processing the audio.")


recognizer = Recognizer()
microphone = Microphone()
with microphone as source:
    recognizer.adjust_for_ambient_noise(source)

stop_listening = recognizer.listen_in_background(microphone, audio_callback)

while True:
    screenshot = desktop_screenshot.read()
    if screenshot is not None:
        cv2.imshow("Desktop", screenshot)
    if cv2.waitKey(1) in [27, ord("q")]:
        break

desktop_screenshot.stop()
cv2.destroyAllWindows()
stop_listening(wait_for_stop=False)
