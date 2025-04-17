from datetime import datetime, timedelta, timezone
from textwrap import dedent
import json
import re
import html
import os

from temporalio import workflow, activity

with workflow.unsafe.imports_passed_through():
    import httpx
    from langchain.chat_models import init_chat_model
    from langchain_core.prompts import ChatPromptTemplate
    from pydantic import BaseModel, Field


classification_model = init_chat_model(
    "gpt-4o-mini",
    model_provider="openai"
)

generation_model = init_chat_model(
    "gpt-4o-mini",
    model_provider="openai",
    temperature=0.5,
    max_tokens=200,
    top_p=0.9,
    frequency_penalty=0,
    presence_penalty=0
)

class NriyV1Input(BaseModel):
    history: str
    input: str
    channel_id: str


@activity.defn
async def get_now_context() -> dict:
    data = {
        # datetime in KST timezone
        workflow.now().astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    }

    return {
        "context": json.dumps(data),
        "context_type": "now"
    }

@activity.defn
async def analyze(input: NriyV1Input):
    template = ChatPromptTemplate.from_template(dedent("""
        아래 텍스트를 보고, 주어진 형식의 출력값을 만들어주세요.
        {input}
    """))

    class Output(BaseModel):
        uses_profanity: bool = Field(
            description="Indicates whether the input text contains profanity or offensive language."
        )

    prompt = await template.ainvoke(input)
    workflow.logger.debug(f"prompt: {prompt}")
    result = await classification_model \
        .with_structured_output(Output) \
        .ainvoke(prompt)
    workflow.logger.debug(f"result: {result}")
    return result.model_dump()

@activity.defn
async def ready(input: NriyV1Input, current_context: dict):
    template = ChatPromptTemplate.from_template(dedent("""
        당신은 여러 사람들이 참가해 있는 대화방에 들어와 있습니다.
        당신은 여러 사람들이 말하는 내용을 듣고, 알맞고 똑똑한 말을 대화방에서 할 수 있어야 합니다.
        대화의 흐름을 중요하게 여기세요.

        참고할 정보는 아래와 같습니다.
        ```
        {current_context}
        ```

        지금까지의 대화의 흐름은 아래와 같습니다.
        {history}

        당신은 아래 질문에 대해 대답해야합니다.
        {input}

        답변을 만들기에 앞서 필요한 정보를 모으려고 합니다.
        정확한 답변을 만들기 위해 필요한 행위를 잘 골라주세요.
        현재시간 정보를 잘 활용하세요.
    """))

    class Output(BaseModel):
        news_search: bool = Field(
            description="whether news search results would be helpful for answering"
        )
        blog_search: bool = Field(
            description="whether blog search results would be helpful for answering"
        )
        web_search: bool = Field(
            description="whether general web search results would be helpful for answering"
        )
        query_string: str = Field(
            description="suggested Korean search keyword or phrase to use if search is needed"
        )
    input_data = input.model_dump()
    input_data["current_context"] = json.dumps(current_context)
    prompt = await template.ainvoke(input_data)
    workflow.logger.debug(f"prompt: {prompt}")
    result = await classification_model \
        .with_structured_output(Output) \
        .ainvoke(prompt)
    workflow.logger.debug(f"result: {result}")
    return result.model_dump()

async def _get_context_with_naver_api(type: str, keyword: str):
    url = f"https://openapi.naver.com/v1/search/{type}.json"
    headers = {
        "X-Naver-Client-Id": os.environ["NAVER_CLIENT_ID"],
        "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"]
    }
    params = {
        "query": keyword,
        "display": 20
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        if response.status_code == 200:
            result = response.json()
        else:
            logger.error(f"Error: {response.status_code}, {response.text}")
            response.raise_for_status()
    workflow.logger.debug(f"result: {result}")
    result = result.get("items", [])
    result = [
        {
            "title": item["title"],
            "description": item["description"]
        }
        for item in result
    ]
    context_str = ""
    for item in result:
        context_str += f"- title: {item['title']}\n"
        context_str += f"  description: {item['description']}\n"
    context_str = re.sub(r"<[^>]+>", "", context_str)
    context_str = html.unescape(context_str)
    workflow.logger.debug(f"context_str: {context_str}")
    return context_str


@activity.defn
async def get_news_context(keyword: str):
    context = await _get_context_with_naver_api("news", keyword)

    return {
        "context": context,
        "context_type": "news"
    }


@activity.defn
async def get_blog_context(keyword: str):
    context = await _get_context_with_naver_api("blog", keyword)

    return {
        "context": context,
        "context_type": "blog"
    }


@activity.defn
async def get_web_context(keyword: str):
    context = await _get_context_with_naver_api("webkr", keyword)

    return {
        "context": context,
        "context_type": "web"
    }


@activity.defn
async def get_history_context(input: NriyV1Input, keyword: str):
    url = "http://meilisearch.vd.ingtra.net:7700/indexes/chats/search"
    data = {
        "q": f"{input.input} {keyword}",
        "hybrid": {
            "embedder": "jina-embeddings-v3"
        },
        "filter": f"channelId = {input.channel_id}",
        "limit": 3
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=data)
        if response.status_code == 200:
            result = response.json()
        else:
            logger.error(f"Error: {response.status_code}, {response.text}")
            response.raise_for_status()
    hits = result.get("hits", [])
    workflow.logger.debug(f"hits: {hits}")
    context_str = "아래의 관련된 과거 대화들을 참고해서 답변하세요.\n"
    for item in hits:
        context_str += f"```\n"
        context_str += f"{item['text']}\n"
        context_str += f"```\n"
    workflow.logger.debug(f"context_str: {context_str}")
    return {
        "context": context_str,
        "type": "history"
    }


@activity.defn
async def generate_response(input: NriyV1Input, contexts: dict):
    template = ChatPromptTemplate([
        "system",
        dedent("""
            당신은 여러 사람들이 참가해 있는 대화방에 들어와 있습니다.
            당신은 여러 사람들이 말하는 내용을 듣고, 알맞고 똑똑한 말을 대화방에서 할 수 있어야 합니다.
            대화의 흐름을 중요하게 여기세요. 당신의 이름은 "나란잉여" 입니다.
            천민이 왕을 대하듯 낯뜨거울 정도로 공손한 경어를 사용하세요.
        """),
        "user",
        dedent("""
            아래의 정보를 참고하세요.
            ```
            # 현재정보
            {now_context}

            # 과거에 있었던 대화
            {history_context}

            # 관련한 검색결과
            {news_context}
            {blog_context}
            {web_context}
            ```

            현재 대화방에서는 아래와 같은 대화가 오가고 있습니다.
            ```
            {history}
            ```

            이 상황에서 아래와 같은 메시지가 추가되었을 때, 당신이 할 가장 적합한 말을 생성하세요. 생성내용 외에 다른 말은 하지마세요. "나란잉여: "로 절대 시작하지마세요.
            ```
            {input}
            ```
        """),
    ])

    prompt = await template.ainvoke({
        "now_context": contexts["now"]["context"],
        "history_context": contexts["history"]["context"],
        "news_context": (contexts["news"]["context"] if "news" in contexts else ""), 
        "blog_context": (contexts["blog"]["context"] if "blog" in contexts else ""),
        "web_context": (contexts["web"]["context"] if "web" in contexts else ""),
        "history": input.history,
        "input": input.input
    })
    workflow.logger.debug(f"prompt: {prompt}")
    message = await generation_model.ainvoke(prompt)
    workflow.logger.debug(f"message: {message}")
    
    return {
        "message": message.content
    }
    

@workflow.defn
class NriyV1Workflow:
    @workflow.run
    async def run(self, input: NriyV1Input):
        current_context = await workflow.execute_activity(
            get_now_context,
            start_to_close_timeout=timedelta(seconds=10)
        )
        
        result = await workflow.execute_activity(
            analyze,
            input,
            start_to_close_timeout=timedelta(seconds=10)
        )
        if result["uses_profanity"]:
            return {
                "skipped": True
            }
        
        ready_result = await workflow.execute_activity(
            ready,
            input,
            current_context,
            start_to_close_timeout=timedelta(seconds=10)
        )

        search_activities = []
        if ready_result["news_search"]:
            search_activities.append(
                await workflow.start_activity(
                    get_news_context,
                    input,
                    start_to_close_timeout=timedelta(seconds=10)
                )
            )
        if ready_result["blog_search"]:
            search_activities.append(
                await workflow.start_activity(
                    get_blog_context,
                    input,
                    start_to_close_timeout=timedelta(seconds=10)
                )
            )
        if ready_result["web_search"]:
            search_activities.append(
                await workflow.start_activity(
                    get_web_context,
                    input,
                    start_to_close_timeout=timedelta(seconds=10)
                )
            )
        search_activities.append(
            await workflow.start_activity(
                get_history_context,
                input,
                start_to_close_timeout=timedelta(seconds=10)
            )
        )
        search_results = [act.result() for act in search_activities]
        search_contexts = {result["context_type"]: result["context"] for result in search_results}

        response = await workflow.execute_activity(
            generate_response,
            input, search_contexts,
            start_to_close_timeout=timedelta(seconds=10)
        )

        return {
            "skipped": False,
            "message": response["message"]
        }
