# pyChatGPTLoop

[![PyPi](https://img.shields.io/pypi/v/pyChatGPTLoop.svg)](https://pypi.python.org/pypi/pyChatGPTLoop)
[![License](https://img.shields.io/github/license/terry3041/pyChatGPT.svg?color=green)](https://github.com/terry3041/pyChatGPT/blob/main/LICENSE)
![PyPi](https://img.shields.io/badge/code_style-black+flake8-blue.svg)



Added backtracking chat on the basis of [terry3041/pyChatGPT](https://github.com/terry3041/pyChatGPT)


## Extra Features

-   [x] Implement asynchronous use
-   [x] can go back to a conversational moment in the past
-   [x] increase the function of initializing personality
-   [x] set local chromedriver 
-   [x] optimized the output, removing two newlines
-   [x] added reply failure handling
-   [x] added GPT-ToolBox[GPT-ToolBox](https://github.com/bigemon/ChatGPT-ToolBox)

## backtracking chat

[![pSurC8S.png](https://s1.ax1x.com/2023/01/12/pSurC8S.png)](https://imgse.com/i/pSurC8S)


## initializing personality


[![pSurS4f.png](https://s1.ax1x.com/2023/01/12/pSurS4f.png)](https://imgse.com/i/pSurS4f)


## Getting Started

> This library is using only the `undetected_chromedriver` to bypass Cloudflare's anti-bot protection.  **Please make sure you have [Google Chrome](https://www.google.com/chrome/) / [Chromium](https://www.chromium.org/) before using this wrapper.**

### Installation

```bash
git clone https://github.com/nek0us/pyChatGPTLoop.git
pip install .

# or

pip install pyChatGPTLoop --upgrade
```

### Usage

#### Obtaining session_token

1. Go to https://chat.openai.com/chat and open the developer tools by `F12`.
2. Find the `__Secure-next-auth.session-token` cookie in `Application` > `Storage` > `Cookies` > `https://chat.openai.com`.
3. Copy the value in the `Cookie Value` field.

![image](https://user-images.githubusercontent.com/19218518/206170122-61fbe94f-4b0c-4782-a344-e26ac0d4e2a7.png)

#### Interactive mode

```bash
python3 -m pyChatGPTLoop
```

#### Import as a module

```python
from pyChatGPTLoop.pyChatGPTLoop import ChatGPT
import asyncio
session_token = 'abc123'  # `__Secure-next-auth.session-token` cookie from https://chat.openai.com/chat
api = ChatGPT(session_token)  # auth with session token
api = ChatGPT(session_token, conversation_id='some-random-uuid')  # specify conversation id
api = ChatGPT(session_token, proxy='https://proxy.example.com:8080')  # specify proxy
api = ChatGPT(session_token, chrome_args=['--window-size=1920,768'])  # specify chrome args
api = ChatGPT(session_token, moderation=False)  # disable moderation
api = ChatGPT(session_token, verbose=True)  # verbose mode (print debug messages)

api = ChatGPT(session_token, driver_path="C:\\yourdriverpath\\chromedriver.exe") # set local chromedriver if you don't wish it update in windows
api = ChatGPT(session_token, driver_path="/yourpath/chromedriver") # set local chromedriver if you don't wish it update in linux
api = ChatGPT(session_token, personality_definition=your List) # the words list of init personality
api = ChatGPT(session_token, toolbox=True) # use GPT-ToolBox

# auth with google login
api = ChatGPT(auth_type='google', email='example@gmail.com', password='password')
# auth with microsoft login
api = ChatGPT(auth_type='microsoft', email='example@gmail.com', password='password')
# auth with openai login (captcha solving using speech-to-text engine)
api = ChatGPT(auth_type='openai', email='example@gmail.com', password='password')
# auth with openai login (manual captcha solving)
api = ChatGPT(
    auth_type='openai', captcha_solver=None,
    email='example@gmail.com', password='password'
)
# auth with openai login (2captcha for captcha solving)
api = ChatGPT(
    auth_type='openai', captcha_solver='2captcha', solver_apikey='abc',
    email='example@gmail.com', password='password'
)
# reuse cookies generated by successful login before login,
# if `login_cookies_path` does not exist, it will process logining  with `auth_type`, and save cookies to `login_cookies_path`
# only works when `auth_type` is `openai` or `google`
api = ChatGPT(auth_type='openai', email='example@xxx.com', password='password',
    login_cookies_path='your_cookies_path',
)


api.reset_conversation()  # reset the conversation
api.clear_conversations()  # clear all conversations

# send message 
resp = asyncio(api.async_send_message('Hello, world!'))
print(resp['message'])

# if in an async function
resp = await api.async_send_message('Hello, world!',msg_type="loop")
print(resp['message'])

# refresh the chat page
await api.refresh_chat_page()  

# return the loop_text conversation
loop_text = "some words"
resp = await api.async_send_message(loop_text,msg_type="loop")

#You can pass the conversation id to the right
resp = await api.async_send_message('Hello, world!',conversation_id,msg_type="msg")

personality_definition = [{"content":r'Now you are going to pretend to be a math teacher called "nothing" to help me with my math',"AI_verify":True}]
await api.init_personality(True,"",personality_definition)

#or 

resp = await api.async_send_message(personality_definition,conversation_id,msg_type="init")

#update session_toekn when chrome running
resp = await api.async_send_message(new_cookie,conversation_id,msg_type="update_cookie")

#all of resp:

resp: dict == {"status":bool,any}
```

## Frequently Asked Questions

### How do i initializing personality?

```bash
# An example of initializing the vocabulary format, the vocabulary content is not representative
personality_definition = [
        {
            "content":r'Now you are going to pretend to be a math teacher called "nothing" to help me with my math',
            "AI_verify":True
            },
        {
            "content":r"You will be very strict in pointing out my mistakes",
            "AI_verify":False
            }
    ]

new_conversation = True
await api.backtrack_chat(new_conversation,"",personality_definition)
# new_conversation : Whether to open a new session for personality initialization, the default is true
# personality_definition: Personality initialization phrase is a list, a single element is a dict, 
# content is the content of the phrase, and AI_verify is a successful detection of personality
# returns a boolean result
```

### How do i go back to the conversation i had?

```bash
# You said some words to chatGPT
loop_text = 'some words'

# Go back to the dialogue where these words last appeared
await api.backtrack_chat(loop_text)
#You can pass the conversation id to the right of loop_text
#return an boolen result

# if you use an async method
resp = await api.async_send_message(loop_text,msg_type="loop")
```

### How do I get it to work on headless linux server?

```bash
# install chromium & X virtual framebuffer
sudo apt install chromium-browser xvfb

# start your script
python3 your_script.py
```
![image](https://user-images.githubusercontent.com/19218518/206170122-61fbe94f-4b0c-4782-a344-e26ac0d4e2a7.png)
### How do I get it to work on Google Colab?

It is normal for the seession to be crashed when installing dependencies. Just ignore the error and run your script.

```python
# install dependencies
!apt install chromium-browser xvfb
!pip install -U selenium_profiles pyChatGPT

# install chromedriver
from selenium_profiles.utils.installer import install_chromedriver
install_chromedriver()
```

```python
# start your script as normal
!python3 -m pyChatGPTLoop
```

## Insipration

This project is inspired by

-   [pyChatGPT](https://github.com/terry3041/pyChatGPT)
-   [ChatGPT](https://github.com/acheong08/ChatGPT)
-   [chatgpt-api](https://github.com/transitive-bullshit/chatgpt-api)

## Disclaimer

This project is not affiliated with OpenAI in any way. Use at your own risk. I am not responsible for any damage caused by this project. Please read the [OpenAI Terms of Service](https://beta.openai.com/terms) before using this project.

## License

This project is licensed under the GPLv3 License - see the [LICENSE](LICENSE) file for details.
