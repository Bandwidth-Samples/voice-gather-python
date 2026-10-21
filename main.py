import http
import os
import sys

import bandwidth
from bandwidth.models.bxml import Response as BxmlResponse
from bandwidth.models.bxml import SpeakSentence, Hangup, Gather
from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
import uvicorn

try:
    BW_ACCOUNT_ID = os.environ['BW_ACCOUNT_ID']
    BW_CLIENT_ID = os.environ['BW_CLIENT_ID']
    BW_CLIENT_SECRET = os.environ['BW_CLIENT_SECRET']
    BW_VOICE_APPLICATION_ID = os.environ['BW_VOICE_APPLICATION_ID']
    BW_NUMBER = os.environ['BW_NUMBER']
    BASE_CALLBACK_URL = os.environ['BASE_CALLBACK_URL']
    LOCAL_PORT = int(os.environ['LOCAL_PORT'])
except KeyError as e:
    print(f"Please set the environmental variables defined in the README\n\n{e}")
    sys.exit(1)
except ValueError as e:
    print(f"Please set the LOCAL_PORT environmental variable to an integer\n\n{e}")
    sys.exit(1)

app = FastAPI()

bandwidth_configuration = bandwidth.Configuration(
    client_id=BW_CLIENT_ID,
    client_secret=BW_CLIENT_SECRET
)

bandwidth_api_client = bandwidth.ApiClient(bandwidth_configuration)
bandwidth_calls_api_instance = bandwidth.CallsApi(bandwidth_api_client)


class CallRequest(BaseModel):
    to: str


@app.exception_handler(RequestValidationError)
def invalid_request(request, exc):
    return Response(status_code=http.HTTPStatus.BAD_REQUEST)


@app.post("/calls", status_code=http.HTTPStatus.OK)
def create_call(call_request: CallRequest):
    create_call_body = bandwidth.CreateCall(
        application_id=BW_VOICE_APPLICATION_ID,
        to=call_request.to,
        var_from=BW_NUMBER,
        answer_url=f"{BASE_CALLBACK_URL}/callbacks/outbound/voice"
    )

    try:
        bandwidth_calls_api_instance.create_call(BW_ACCOUNT_ID, create_call_body)
    except Exception as e:
        print(f"Failed to create call: {e}")
        return Response(status_code=http.HTTPStatus.INTERNAL_SERVER_ERROR)


@app.post("/callbacks/outbound/voice", status_code=http.HTTPStatus.OK)
def outbound_voice(answer_callback: bandwidth.models.AnswerCallback):
    bxml = BxmlResponse()

    match answer_callback.event_type:
        case "answer":
            speak_sentence = SpeakSentence(
                text="Press 1 to choose option 1. Press 2 to choose option 2. Press pound when you are finished."
            )
            gather = Gather(
                gather_url="/callbacks/outbound/voice/gather",
                terminating_digits="#",
                audio_verbs=[speak_sentence]
            )
            bxml.add_verb(gather)
        case "initiate":
            speak_sentence = SpeakSentence(text="Initiate event received but not intended. Ending call.")
            hangup = Hangup()
            bxml.add_verb(speak_sentence)
            bxml.add_verb(hangup)
        case "disconnect":
            print(f"Call {answer_callback.call_id} has disconnected")
        case _:
            print(f"Unexpected event type {answer_callback.event_type} received")

    return Response(content=bxml.to_bxml(), media_type="application/xml")


@app.post("/callbacks/outbound/voice/gather", status_code=http.HTTPStatus.OK)
def gather(gather_callback: bandwidth.models.GatherCallback):
    if gather_callback.event_type != "gather":
        print(f"Unexpected event type {gather_callback.event_type} received")
        return Response(status_code=http.HTTPStatus.BAD_REQUEST)

    match gather_callback.digits:
        case "1":
            speak_sentence = SpeakSentence("You chose option 1. Goodbye.")
        case "2":
            speak_sentence = SpeakSentence("You chose option 2. Goodbye.")
        case _:
            speak_sentence = SpeakSentence("You did not choose a valid option. Goodbye.")

    bxml = BxmlResponse([speak_sentence])
    return Response(content=bxml.to_bxml(), media_type="application/xml")


if __name__ == "__main__":
    uvicorn.run("main:app", port=LOCAL_PORT, reload=True)
