# api_utils.py
import requests
from openai import OpenAI
import streamlit as st
from db_utils import conn, get_cursor

def web_search(query, api_key):
    """执行谷歌搜索并返回格式化结果"""
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {
        "q": query,
        "gl": "cn",
        "hl": "zh-cn",
        "num": 5  # 获取前5条结果
    }

    try:
        response = requests.post(
            "https://google.serper.dev/search",
            headers=headers,
            json=payload,
            timeout=10
        )
        results = response.json()

        search_context = "\n".join([
            f"• [{item['title']}]({item['link']})\n  {item['snippet']}"
            for item in results.get("organic", [])[:3]  # 取前3条结果
        ])
        return f"**网络搜索结果**\n{search_context}\n\n"

    except Exception as e:
        st.error(f"搜索失败: {str(e)}")
        return ""

def get_active_api_config():
    """获取当前激活的API配置"""
    with get_cursor() as c: 
        c.execute("""
            SELECT base_url, api_key, model_name 
            FROM api_configurations 
            WHERE is_active = 1 
            LIMIT 1
        """)
        result = c.fetchone()
    return result or ("https://api.deepseek.com/v1", "", "deepseek-r1")

def process_stream(stream, used_key):
    """合并处理思考阶段和响应阶段"""
    thinking_content = ""
    response_content = ""
    
    # 在状态块外部预先创建响应占位符
    response_placeholder = st.empty()
    total_count = 0
    chunk_num = 0
    
    with st.status("思考中...", expanded=True) as status:
        thinking_placeholder = st.empty()
        thinking_phase = True  # 思考阶段标记
        
        for chunk in stream:
            chunk_num += 1
            # 解析数据块
            reasoning = chunk.choices[0].delta.reasoning_content or ""
            content = chunk.choices[0].delta.content or ""
            role = chunk.choices[0].delta.role or ""
            # 处理思考阶段
            if thinking_phase:
                thinking_content += reasoning
                thinking_placeholder.markdown(thinking_content)
                
                # 检测思考阶段结束
                if content:
                    status.update(label="思考完成", state="complete", expanded=False)
                    thinking_phase = False
                    response_placeholder.markdown("▌")  # 初始化响应光标

            # 处理响应阶段（无论是否在思考阶段都收集内容）
            response_content += content
            if not thinking_phase:
                response_placeholder.markdown(response_content + "▌")

            # 更新Token使用
            adjusted_length = sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in (reasoning + content))
            total_count += adjusted_length
            if chunk_num % 10 == 0:
                with get_cursor() as c: 
                    c.execute(
                        "UPDATE api_keys SET used_tokens = used_tokens + ? WHERE key = ?",
                        (total_count, used_key)
                    )
                    total_count = 0

        # 流结束后移除光标
        response_placeholder.markdown(response_content)
        with get_cursor() as c: 
                    c.execute(
                        "UPDATE api_keys SET used_tokens = used_tokens + ? WHERE key = ?",
                        (total_count, used_key)
                    )
    
    return f"<think>{thinking_content}</think>{response_content}"