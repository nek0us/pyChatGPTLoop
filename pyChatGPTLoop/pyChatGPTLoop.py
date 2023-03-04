from functools import partial
from selenium.webdriver.support import expected_conditions as EC
from selenium.common import exceptions as SeleniumExceptions
from selenium.webdriver.support.ui import WebDriverWait   # type: ignore
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By

import undetected_chromedriver as uc
from markdownify import markdownify
from threading import Thread
import platform
import logging
import json
import time
import re
import os
import asyncio 
import threading


cf_challenge_form = (By.ID, 'challenge-form')

chatgpt_textbox = (By.TAG_NAME, 'textarea')
chatgpt_streaming = (By.CLASS_NAME, 'result-streaming')
chatgpt_big_response = (By.XPATH, '//div[@class="flex-1 overflow-hidden"]//div[p]')
chatgpt_small_response = (
    By.XPATH,
    '//div[starts-with(@class, "markdown prose w-full break-words")]',
)
chatgpt_alert = (By.XPATH, '//div[@role="alert"]')
chatgpt_intro = (By.ID, 'headlessui-portal-root')
chatgpt_login_btn = (By.XPATH, '//button[text()="Log in"]')
chatgpt_login_h1 = (By.XPATH, '//h1[text()="Welcome back"]')
chatgpt_logged_h1 = (By.XPATH, '//h1[text()="ChatGPT"]')

chatgpt_new_chat = (By.LINK_TEXT, 'New chat')
chatgpt_clear_convo = (By.LINK_TEXT, 'Clear conversations')
chatgpt_confirm_clear_convo = (By.LINK_TEXT, 'Confirm clear conversations')
chatgpt_chats_list_first_node = (
    By.XPATH,
    '//div[substring(@class, string-length(@class) - string-length("text-sm") + 1)  = "text-sm"]//a',
)

chatgpt_chat_url = 'https://chat.openai.com/chat'


class ChatGPT:
    '''
    An unofficial Python wrapper for OpenAI's ChatGPT API
    '''

    def __init__(
        self,
        session_token: str = None,   # type: ignore
        conversation_id: str = '',
        auth_type: str = None,  # type: ignore
        email: str = None,  # type: ignore
        password: str = None,  # type: ignore
        login_cookies_path: str = '',
        captcha_solver: str = 'pypasser',
        solver_apikey: str = '',
        proxy: str = None,  # type: ignore
        chrome_args: list = [],
        moderation: bool = True,
        verbose: bool = False,
        driver_path: str = '',
        personality_definition: list = [],
        toolbox: bool = False
    ):
        '''
        Initialize the ChatGPT object\n
        :param session_token: The session token to use for authentication
        :param conversation_id: The conversation ID to use for the chat session
        :param auth_type: The authentication type to use (`google`, `microsoft`, `openai`)
        :param email: The email to use for authentication
        :param password: The password to use for authentication
        :param login_cookies_path: The path to the cookies file to use for authentication
        :param captcha_solver: The captcha solver to use (`pypasser`, `2captcha`)
        :param solver_apikey: The apikey of the captcha solver to use (if any)
        :param proxy: The proxy to use for the browser (`https://ip:port`)
        :param chrome_args: The arguments to pass to the browser
        :param moderation: Whether to enable message moderation
        :param verbose: Whether to enable verbose logging
        '''
        self.__init_logger(verbose)

        self.__session_token = session_token
        self.__conversation_id = conversation_id
        self.__auth_type = auth_type
        self.__email = email
        self.__password = password
        self.__login_cookies_path = login_cookies_path
        self.__captcha_solver = captcha_solver
        self.__solver_apikey = solver_apikey
        self.__proxy = proxy
        self.__chrome_args = chrome_args
        self.__moderation = moderation
        self.__driver_path = driver_path
        self.__personality_definition = personality_definition
        self.__toolbox = toolbox

        if not self.__session_token and (
            not self.__email or not self.__password or not self.__auth_type
        ):
            raise ValueError(
                'Please provide either a session token or login credentials'
            )
        if self.__auth_type not in [None, 'google', 'microsoft', 'openai']:
            raise ValueError('Invalid authentication type')
        if self.__captcha_solver not in [None, 'pypasser', '2captcha']:
            raise ValueError('Invalid captcha solver')
        if self.__captcha_solver == '2captcha' and not self.__solver_apikey:
            raise ValueError('Please provide a 2captcha apikey')
        if self.__proxy and not re.findall(
            r'(https?|socks(4|5)?):\/\/.+:\d{1,5}', self.__proxy
        ):
            raise ValueError('Invalid proxy format')
        if self.__auth_type == 'openai' and self.__captcha_solver == 'pypasser':
            try:
                import ffmpeg_downloader as ffdl  # type: ignore
            except ModuleNotFoundError:
                raise ValueError(
                    'Please install ffmpeg_downloader, PyPasser, and pocketsphinx by running `pip install ffmpeg_downloader PyPasser pocketsphinx`'
                )

            ffmpeg_installed = bool(ffdl.ffmpeg_version)
            self.logger.debug(f'ffmpeg installed: {ffmpeg_installed}')
            if not ffmpeg_installed:
                import subprocess as sp

                sp.run(['ffdl', 'install'])
            os.environ['PATH'] += os.pathsep + ffdl.ffmpeg_dir

        # async_loop
        self.rec = []
        self.msg_id:int = 0
        self.send_queue = asyncio.Queue()
        self.event_loop_browser = asyncio.new_event_loop()
        self.event_loop_gpt = asyncio.new_event_loop()
        threading.Thread(target=lambda: self.run_loop(self.event_loop_browser),daemon=True).start()
        threading.Thread(target=lambda: self.run_loop(self.event_loop_gpt),daemon=True).start()
        asyncio.run_coroutine_threadsafe(self.__init_browser(),self.event_loop_browser)
        asyncio.run_coroutine_threadsafe(self.loop_gpt(),self.event_loop_gpt)
        

    def run_loop(self,loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()
    
            
    def __del__(self):
        '''
        Close the browser and display
        '''
        self.__is_active = False
        if hasattr(self, 'driver'):
            self.logger.debug('Closing browser...')
            self.driver.quit()
        if hasattr(self, 'display'):
            self.logger.debug('Closing display...')
            self.display.stop()
       
        

    def __init_logger(self, verbose: bool) -> None:
        '''
        Initialize the logger\n
        :param verbose: Whether to enable verbose logging
        '''
        self.logger = logging.getLogger('pyChatGPT')
        self.logger.setLevel(logging.DEBUG)
        if verbose:
            formatter = logging.Formatter('[%(funcName)s] %(message)s')
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(stream_handler)

    async def __init_browser(self) -> None:
        '''
        Initialize the browser
        '''
        if platform.system() == 'Linux' and 'DISPLAY' not in os.environ:
            self.logger.debug('Starting virtual display...')
            try:
                from pyvirtualdisplay import Display  # type: ignore

                self.display = Display()
            except ModuleNotFoundError:
                raise ValueError(
                    'Please install PyVirtualDisplay to start a virtual display by running `pip install PyVirtualDisplay`'
                )
            except FileNotFoundError as e:
                if 'No such file or directory: \'Xvfb\'' in str(e):
                    raise ValueError(
                        'Please install Xvfb to start a virtual display by running `sudo apt install xvfb`'
                    )
                raise e
            self.display.start()

        self.logger.debug('Initializing browser...')
        options = uc.ChromeOptions()
        options.add_argument('--window-size=1024,768')
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        
        if self.__proxy:
            options.add_argument(f'--proxy-server={self.__proxy}')
        for arg in self.__chrome_args:
            options.add_argument(arg)
        try:
            self.driver = uc.Chrome(options=options,driver_executable_path=self.__driver_path)
        except TypeError as e:
            if str(e) == 'expected str, bytes or os.PathLike object, not NoneType':
                raise ValueError('Chrome installation not found')
            raise e

        if self.__login_cookies_path and os.path.exists(self.__login_cookies_path):
            self.logger.debug('Restoring cookies...')
            try:
                with open(self.__login_cookies_path, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                for cookie in cookies:
                    if cookie['name'] == '__Secure-next-auth.session-token':
                        self.__session_token = cookie['value']
            except json.decoder.JSONDecodeError:
                self.logger.debug(f'Invalid cookies file: {self.__login_cookies_path}')

        if self.__session_token:
            self.logger.debug('Restoring session_token...')
            self.driver.execute_cdp_cmd(
                'Network.setCookie',
                {
                    'domain': 'chat.openai.com',
                    'path': '/',
                    'name': '__Secure-next-auth.session-token',
                    'value': self.__session_token,
                    'httpOnly': True,
                    'secure': True,
                },
            )

        if not self.__moderation:
            self.logger.debug('Blocking moderation...')
            self.driver.execute_cdp_cmd(
                'Network.setBlockedURLs',
                {'urls': ['https://chat.openai.com/backend-api/moderations']},
            )

        self.logger.debug('Ensuring Cloudflare cookies...')
        await self.__ensure_cf()

        self.logger.debug('Opening chat page...')
        self.driver.get(f'{chatgpt_chat_url}/{self.__conversation_id}')
        self.__check_blocking_elements()

        self.__is_active = True
        Thread(target=self.__keep_alive, daemon=True).start()

    async def __ensure_cf(self, retry: int = 5) -> None:
        '''
        Ensure Cloudflare cookies are set\n
        :param retry: Number of retries
        '''
        
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
            """
        })
        self.logger.debug('Opening new tab...')
        original_window = self.driver.current_window_handle
        self.driver.switch_to.new_window('tab')

        self.logger.debug('Getting Cloudflare challenge...')
        while True:
            self.driver.get('https://chat.openai.com/api/auth/session')
            
            try:
                # ok?
                WebDriverWait(self.driver, 10).until(
                            
                        EC.presence_of_element_located((By.XPATH, "//body"))
                    ) 
                WebDriverWait(self.driver, 10).until(
                            
                        EC.presence_of_element_located((By.XPATH, "//pre[contains(text(), 'accessToken')]"))
                    ) 
                self.driver.execute_script("return JSON.parse(document.body.innerText)")
                
            except:
                # no,it's cf 
                try:
                    # check cf button
                    cf_button = False
                    try:
                        
                        cf_button_find = WebDriverWait(self.driver, 10).until(
                            
                        EC.visibility_of_element_located((By.XPATH, '//*[@id="challenge-stage"]/div/input'))
                    ) 
                        cf_button = True
                    except:
                        pass
                    
                    if cf_button:
                    
                        cf_button_find = WebDriverWait(self.driver, 5).until(
                        EC.visibility_of_element_located((By.XPATH, '//*[@id="cf-stage"]/div[6]/label/span'))
                    ) 
                        cf_button_find.click()
                        
                    else:
                        # try:
                        iframe = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.XPATH, '/html/body/div/div[2]/form/div[4]/div/div/iframe'))
                        )
                        self.driver.switch_to.frame(iframe)
                        
                        
                        cf_button_find = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, '/html/body/table/tbody/tr/td/div/div[1]/table/tbody/tr/td[1]/div[6]/label'))
                    ) 
                        cf_button_find.click()
                    
                except SeleniumExceptions.TimeoutException:
                    
                    self.logger.debug(f'Cloudflare challenge failed, retrying {retry}...')
                    self.driver.save_screenshot(f'cf_failed_{retry}.png')
                    if retry > 0:
                        self.logger.debug('Closing tab...')
                        self.driver.close()
                        self.driver.switch_to.window(original_window)
                        return await self.__ensure_cf(retry - 1)
                    raise ValueError('Cloudflare challenge failed')
                except ValueError:
                    break
            
            WebDriverWait(self.driver, 10).until(
                        
                    EC.presence_of_element_located((By.XPATH, "//pre[contains(text(), 'accessToken')]"))
                ) 
            self.logger.debug('Cloudflare challenge passed')
            
            
            self.logger.debug('Validating authorization...')
            try:
                #await asyncio.sleep(1)
                response = json.dumps(self.driver.execute_script("return JSON.parse(document.body.innerText)"))
                break
            except:
                pass
            
        response = json.dumps(self.driver.execute_script("return JSON.parse(document.body.innerText)"))
        
        if response[0] != '{':
            response = self.driver.find_element(By.TAG_NAME, 'pre').text
        response = json.loads(response)
        if (not response) or (
            'error' in response and response['error'] == 'RefreshAccessTokenError'
        ):
            self.logger.debug('Authorization is invalid')
            if not self.__auth_type:
                raise ValueError('Invalid session token')
            self.__login()
        self.logger.debug('Authorization is valid')

        self.logger.debug('Closing tab...')
        self.driver.close()
        self.driver.switch_to.window(original_window)

    def __check_capacity(self, target_url: str):
        '''
        Check if ChatGPT is at capacity\n
        :param target_url: URL to retry if ChatGPT is at capacity
        '''
        while True:
            try:
                self.logger.debug('Checking if ChatGPT is at capacity...')
                WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located(
                        (By.XPATH, '//div[text()="ChatGPT is at capacity right now"]')
                    )
                )
                self.logger.debug('ChatGPT is at capacity, retrying...')
                self.driver.get(target_url)
            except SeleniumExceptions.TimeoutException:
                self.logger.debug('ChatGPT is not at capacity')
                break

    def __login(self) -> None:
        '''
        Login to ChatGPT
        '''
        self.logger.debug('Opening new tab...')
        original_window = self.driver.current_window_handle
        self.driver.switch_to.new_window('tab')

        self.logger.debug('Opening login page...')
        self.driver.get('https://chat.openai.com/auth/login')
        self.__check_capacity('https://chat.openai.com/auth/login')

        self.logger.debug('Clicking login button...')
        WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable(chatgpt_login_btn)
        ).click()

        WebDriverWait(self.driver, 5).until(
            EC.presence_of_element_located(chatgpt_login_h1)
        )

        from . import Auth0

        Auth0.login(self)

        self.logger.debug('Checking if login was successful')
        try:
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(chatgpt_logged_h1)
            )
            if self.__login_cookies_path:
                self.logger.debug('Saving cookies...')
                with open(self.__login_cookies_path, 'w', encoding='utf-8') as f:
                    json.dump(
                        [
                            i
                            for i in self.driver.get_cookies()
                            if i['name'] == '__Secure-next-auth.session-token'
                        ],
                        f,
                    )
        except SeleniumExceptions.TimeoutException as e:
            self.driver.save_screenshot('login_failed.png')
            raise e

        self.logger.debug('Closing tab...')
        self.driver.close()
        self.driver.switch_to.window(original_window)

    def __keep_alive(self) -> None:
        '''
        Keep the session alive by updating the local storage\n
        Credit to Rawa#8132 in the ChatGPT Hacking Discord server
        '''
        while self.__is_active:
            self.logger.debug('Updating session...')
            payload = (
                '{"event":"session","data":{"trigger":"getSession"},"timestamp":%d}'
                % int(time.time())
            )
            try:
                self.driver.execute_script(
                    'window.localStorage.setItem("nextauth.message", arguments[0])',
                    payload,
                )
            except Exception as e:
                self.logger.debug(f'Failed to update session: {str(e)}')
            time.sleep(60)

    def __check_blocking_elements(self) -> None:
        '''
        Check for blocking elements and dismiss them
        '''
        self.logger.debug('Looking for blocking elements...')
        try:
            intro = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located(chatgpt_intro)
            )
            self.logger.debug('Dismissing intro...')
            self.driver.execute_script('arguments[0].remove()', intro)
        except SeleniumExceptions.TimeoutException:
            pass

        alerts = self.driver.find_elements(*chatgpt_alert)
        if alerts:
            self.logger.debug('Dismissing alert...')
            self.driver.execute_script('arguments[0].remove()', alerts[0])

    def __stream_message(self):
        prev_content = ''
        while True:
            result_streaming = self.driver.find_elements(*chatgpt_streaming)
            responses = self.driver.find_elements(*chatgpt_big_response)
            if responses:
                response = responses[-1]
                if 'text-red' in response.get_attribute('class'):
                    self.logger.debug('Response is an error')
                    raise ValueError(response.text)
            response = self.driver.find_elements(*chatgpt_small_response)[-1]
            content = response.text
            if content != prev_content:
                yield content[len(prev_content) :]
                prev_content = content
            if not result_streaming:
                break

    async def send_message(self, conversation_id: str, message: str, stream: bool = False ) -> dict:
        '''
        please use async_send_message,
        Send a message to ChatGPT\n
        :param message: Message to send
        :return: Dictionary with keys `message` and `conversation_id`
        ''' 
        await self.cf(conversation_id)
        res_code = await self.regenerate_error()
        if res_code == 0:
            return {'message': "regenerate error! retries exceeded.", 'conversation_id': conversation_id}
        elif res_code == 2:
            return {'message': "Sorry,please ask again.", 'conversation_id': conversation_id}
        
        #await asyncio.sleep(2)
        self.logger.debug('Wait...')
        wait = WebDriverWait(self.driver, 20)
        elements = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//div[@class='min-h-[20px] flex flex-col items-start gap-4 whitespace-pre-wrap']")))

        #await asyncio.sleep(1)
        if self.__toolbox:
            self.driver.execute_script(
            r'''javascript:var pageSource=document.documentElement.outerHTML;-1!==pageSource.indexOf('cf-spinner-please-wait')||window.oofPatch||(window.oofPatch=!0,pageSource=pageSource.replace(/\"oof\":true/g,'"oof":false'),document.open(),document.write(pageSource),document.close()),window.enableFakeMod='false'!=localStorage.getItem('enable_fakemod');var style=document.createElement('style');style.innerHTML='.switch{position:relative;display:inline-block;width:60px;height:34px;}.switch input{opacity:0;width:0;height:0;}.slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background-color:#ccc;-webkit-transition:.4s;transition:.4s;}.slider:before{position:absolute;content:"";height:26px;width:26px;left:4px;bottom:4px;background-color:white;-webkit-transition:.4s;transition:.4s;}input:checked + .slider{background-color:#2196F3;}input:focus + .slider{box-shadow:0 0 1px #2196F3;}input:checked + .slider:before{-webkit-transform:translateX(26px);-ms-transform:translateX(26px);transform:translateX(26px);}.slider.round{border-radius:34px;}.slider.round:before{border-radius:50%;}',document.head.appendChild(style),window.switchEnableFakeMod=function(){var a=document.querySelector('input#cswitch'),b=!!a&&a.checked;b?(window.enableFakeMod=!0,localStorage.setItem('enable_fakemod',!0)):(window.enableFakeMod=!1,localStorage.setItem('enable_fakemod',!1))},window.clearAllBoxItem=function(){for(var c,a=document.querySelectorAll('nav'),b=0;b<a.length;b++){c=a[b].querySelectorAll('div.toolbox-item');for(var d=0;d<c.length;d++)c[d].remove()}},window.exportSaveData=function(){var a=window.conversation_id_last||'',b=window.parent_message_id_last||'',c=window.authorization_last;if(''==a||''==b||'undefined'==a||'undefined'==b)return void alert('\u8BF7\u81F3\u5C11\u8BF4\u4E24\u53E5\u8BDD\u518D\u4F7F\u7528\u8FD9\u4E2A\u529F\u80FD!');var e=JSON.stringify({conversation_id:a,parent_message_id:b,authorization:c}),f=window.btoa(e);return f},window.importSaveData=function(a){var b=window.atob(a),c=JSON.parse(b);if(!c||void 0===c.conversation_id||void 0===c.parent_message_id)return void alert('\u4F1A\u8BDD\u5B58\u6863\u5DF2\u635F\u574F, \u8BF7\u786E\u4FDD\u5B8C\u6574\u590D\u5236!');var d=window.getAuthTimestamp(c.authorization)||0;if(!(d&&Math.floor(Date.now()/1e3)>d))alert('\u8FD9\u4E2A\u4F1A\u8BDD\u5B58\u6863\u7684\u6709\u6548\u671F\u6700\u957F\u81F3\uFF1A\r\n'+new Date(1e3*d).toLocaleString('en-US')+'\r\n\r\n\u8BF7\u6CE8\u610F:\u5BFC\u5165\u7684\u4F1A\u8BDD\u65E0\u6CD5\u88AB\u518D\u6B21\u5BFC\u51FA\uFF0C\u4E5F\u65E0\u6CD5\u4FDD\u5B58'),window.import_authorization=c.authorization;else if(!confirm('\u8FD9\u4E2A\u4F1A\u8BDD\u5B58\u6863\u7684Token\u770B\u8D77\u6765\u5DF2\u8FC7\u671F\uFF0C\u6216\u8BB8\u65E0\u6CD5\u6B63\u5E38\u5DE5\u4F5C\u3002\r\n\u5047\u5982\u8FD9\u4E2A\u5B58\u6863\u662F\u7531\u5F53\u524D\u8D26\u53F7\u6240\u5BFC\u51FA\uFF0C\u60A8\u53EF\u4EE5\u5C1D\u8BD5\u4F7F\u7528\u5F53\u524D\u4F1A\u8BDD\u8986\u76D6\u5BFC\u5165\u7684\u72B6\u6001\u3002\r\n\u662F\u5426\u7EE7\u7EED\uFF1F'))return;window.next_conversation_id=c.conversation_id,window.next_parent_message_id=c.parent_message_id,alert('\u5BFC\u5165\u6210\u529F,\u5F53\u524D\u4F1A\u8BDD\u72B6\u6001\u5DF2\u300C\u6682\u65F6\u300D\u9644\u52A0\u5230\u5BFC\u5165\u7684\u5B58\u6863\u3002\u8FD9\u5C06\u5BF9\u60A8\u7684\u4E0B\u4E00\u53E5\u8BDD\u751F\u6548\u3002\r\n\u5982\u679C\u8BE5\u5B58\u6863\u7684\u5BBF\u4E3B\u5DF2\u9000\u51FA\u767B\u5F55\u6216\u91CA\u653E\u8BE5\u4F1A\u8BDD\uFF0C\u5219\u5B58\u6863\u4E5F\u4F1A\u4E00\u8D77\u5931\u6548\r\n\u6B64\u65F6\u60A8\u53EF\u80FD\u4F1A\u88AB\u63D0\u793A\u767B\u5F55\u8FC7\u671F\u3002\r\n\r\n\u82E5\u8981\u4E2D\u9014\u89E3\u9664\u9644\u52A0\u72B6\u6001\u3002\u8BF7\u5237\u65B0\u6D4F\u89C8\u5668\u3001\u70B9\u51FB\u300C +New chat \u300D\u65B0\u5EFA\u4F1A\u8BDD\u6216\u5207\u6362\u5230\u5176\u5B83\u7684\u4F1A\u8BDD\u3002')},window.clearTempValues=function(){delete window.import_authorization,delete window.next_parent_message_id,delete window.next_conversation_id,delete window.parent_message_id_last,delete window.conversation_id_last,delete window.authorization_last},window.boxInit=function(){window.clearAllBoxItem();for(var a=document.querySelectorAll('nav'),b=function _loop(){var e=a[c],f=document.createElement('div'),g=e.querySelectorAll('a');e.childNodes[0].hasOwnProperty('patched')||(e.childNodes[0].addEventListener('click',function(l){l.preventDefault(),confirm('\u5373\u5C06\u521B\u5EFA\u65B0\u7684\u4F1A\u8BDD, \u4F7F\u7528\u5BFC\u5165\u529F\u80FD\u5BFC\u5165\u7684\u4F1A\u8BDD\u5C06\u5931\u6548,\u662F\u5426\u7EE7\u7EED?')&&(e.childNodes[0].removeEventListener('click',arguments.callee),window.clearTempValues(),e.childNodes[0].click())}),Object.defineProperty(e.childNodes[0],'patched',{value:!0,enumerable:!1})),f.setAttribute('class','toolbox-item flex py-3 px-3 items-center gap-3 rounded-md hover:bg-gray-500/10 transition-colors duration-200 text-white cursor-pointer text-sm flex-shrink-0 border border-white/20'),f.innerHTML='<svg t="1670527970700" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="9830" width="18" height="18"><path d="M514 114.3c-219.9 0-398.8 178.9-398.8 398.8 0 220 178.9 398.9 398.8 398.9s398.8-178.9 398.8-398.8S733.9 114.3 514 114.3z m0 685.2c-42 0-76.1-34.1-76.1-76.1 0-42 34.1-76.1 76.1-76.1 42 0 76.1 34.1 76.1 76.1 0 42.1-34.1 76.1-76.1 76.1z m0-193.8c-50.7 0-91.4-237-91.4-287.4 0-50.5 41-91.4 91.5-91.4s91.4 40.9 91.4 91.4c-0.1 50.4-40.8 287.4-91.5 287.4z" p-id="9831" fill="#dbdbdb"></path></svg>\u7981\u7528\u6570\u636E\u76D1\u7BA1<label class="switch" style="position: absolute; right: 15px;"><input id="cswitch" type="checkbox" '+(window.enableFakeMod?'checked=\'true\'':'')+' onclick="window.switchEnableFakeMod()" ><span class="slider"></span></label>',e.insertBefore(f,e.childNodes[1]);var h=document.createElement('div');h.setAttribute('class','toolbox-item flex py-3 px-3 items-center gap-3 rounded-md hover:bg-gray-500/10 transition-colors duration-200 text-white cursor-pointer text-sm flex-shrink-0 border border-white/20'),h.innerHTML='\n        <button id="exportSession" class="btn flex justify-center gap-2 btn-dark btn-small m-auto mb-2">\n            <svg t="1670527911492" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="8753" width="16" height="16"><path d="M562.996016 643.229748V72.074369a50.996016 50.996016 0 0 0-101.992032 0v571.155379a50.996016 50.996016 0 0 0 101.992032 0z" fill="#dbdbdb" p-id="8754"></path><path d="M513.087915 144.080744L802.337317 432.446215a50.996016 50.996016 0 0 0 71.93838-72.210358L513.087915 0 149.588313 362.411687A50.996016 50.996016 0 0 0 221.594688 434.486056L513.087915 144.148738zM53.035857 643.229748v184.537583c0 109.471448 105.255777 192.832935 230.026029 192.832935h457.876228c124.770252 0 230.026029-83.361487 230.026029-192.832935V643.229748a50.996016 50.996016 0 1 0-101.992031 0v184.537583c0 47.256308-55.075697 90.840903-128.033998 90.840903H283.061886c-72.9583 0-128.033997-43.65259-128.033998-90.840903V643.229748a50.996016 50.996016 0 0 0-101.992031 0z" fill="#dbdbdb" p-id="8755"></path></svg>\n            \u5BFC\u51FA\u4F1A\u8BDD\n        </button>\n        <button id="importSession" class="btn flex justify-center gap-2 btn-dark btn-small m-auto mb-2">\n            <svg t="1670527878930" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="7606" width="16" height="16"><path d="M563.2 68.266667v573.44a51.2 51.2 0 0 1-102.4 0V68.266667a51.2 51.2 0 0 1 102.4 0z" fill="#dbdbdb" p-id="7607"></path><path d="M513.092267 616.584533l290.474666-289.518933a51.2 51.2 0 0 1 72.226134 72.4992L513.092267 761.173333 148.138667 397.448533A51.2 51.2 0 0 1 220.433067 324.949333l292.6592 291.6352z" fill="#dbdbdb" p-id="7608"></path><path d="M51.2 641.706667v185.275733c0 109.909333 105.6768 193.604267 230.946133 193.604267h459.707734c125.269333 0 230.946133-83.694933 230.946133-193.604267V641.706667a51.2 51.2 0 1 0-102.4 0v185.275733c0 47.445333-55.296 91.204267-128.546133 91.204267H282.146133c-73.250133 0-128.546133-43.8272-128.546133-91.204267V641.706667a51.2 51.2 0 0 0-102.4 0z" fill="#dbdbdb" p-id="7609"></path></svg>\n            \u5BFC\u5165\u4F1A\u8BDD\n        </button>\n        ';var j=h.querySelector('#exportSession');j.onclick=function(){var l=document.querySelector('textarea'),m=window.exportSaveData();m&&prompt('\u2193\u8BF7\u590D\u5236\u60A8\u7684\u4F1A\u8BDD\u5B58\u6863\u2193',m)};var k=h.querySelector('#importSession');for(k.onclick=function(){if(!window.location.href.includes('/chat/')&&window.location.href.includes('/chat'))return void alert('\u8BF7\u5728\u4E00\u4E2A\u60A8\u5DF2\u7ECF\u5B58\u5728\u7684\u4F1A\u8BDD\u4F7F\u7528\u8FD9\u4E2A\u529F\u80FD\uFF0C\r\n\u800C\u4E0D\u662F\u5728\u300C New Chat \u300D\u7684\u7A7A\u4F1A\u8BDD\u4E0A\u4E0B\u6587\u91CC\u9644\u52A0');var l=prompt('\u8BF7\u5728\u6B64\u7C98\u8D34\u4F1A\u8BDD\u5B58\u6863');window.importSaveData(l)},e.insertBefore(h,e.childNodes[1]),d=0;d<g.length;d++)e.childNodes[0].hasOwnProperty('patched')||(e.childNodes[0].addEventListener('click',function(l){l.preventDefault(),confirm('\u5373\u5C06\u521B\u5EFA\u65B0\u7684\u4F1A\u8BDD, \u4F7F\u7528\u5BFC\u5165\u529F\u80FD\u5BFC\u5165\u7684\u4F1A\u8BDD\u5C06\u5931\u6548,\u662F\u5426\u7EE7\u7EED?')&&(e.childNodes[0].removeEventListener('click',arguments.callee),window.clearTempValues(),e.childNodes[0].click())}),Object.defineProperty(e.childNodes[0],'patched',{value:!0,enumerable:!1}))},c=0;c<a.length;c++){var d;b()}},window.getAuthTimestamp=function(a){var b=a.split('.');if(2>b.length)return 0;var c=window.atob(b[1]),d=JSON.parse(c);return d&&d.exp?d.exp:0},window.boxInit();var oldFetch=window.fetch;window.fetch=function(){for(var a=arguments.length,b=Array(a),c=0;c<a;c++)b[c]=arguments[c];if(b[0].includes('moderations')&&window.enableFakeMod)return new Response('{}',{status:200,statusText:'ok'});if(b[0].includes('signout')&&window.enableFakeMod&&!confirm('\u662F\u5426\u8981\u9000\u51FA\u767B\u5F55\uFF1F'))return new Response('{}',{status:200,statusText:'ok'});if(b[0].includes('/conversation/')||b[0].includes('/conversations')||b[0].includes('/chat.json')){if(b[0].includes('/conversations')&&'PATCH'===b[1].method){var e=JSON.parse(b[1].body);e.is_visible=!(confirm('\u8B66\u544A:\u771F\u7684\u8981\u6E05\u7A7A\u60A8\u8D26\u6237\u4E0B\u6240\u6709\u7684\u4F1A\u8BDD\u8BB0\u5F55\uFF1F')&&confirm('\u8B66\u544A:\u7B2C\u4E8C\u6B21\u786E\u8BA4,\u6E05\u7A7A\u540E\u60A8\u5C06\u65E0\u6CD5\u627E\u56DE\u4E4B\u524D\u7684\u6240\u6709\u8BB0\u5F55!\u662F\u5426\u7EE7\u7EED\uFF1F')),e.is_visible||window.clearTempValues(),b[1].body=JSON.stringify(e)}setTimeout(window.onresize,1e3),window.clearTempValues()}else if(b[0].includes('conversation')&&b[1].body&&'POST'===b[1].method){var d=new Headers(b[1].headers),e=d.get('authorization');window.authorization_last=e;var f=window.import_authorization?window.import_authorization:e;if(d.set('authorization',f),b[1].headers=d,window.next_conversation_id&&window.next_parent_message_id){var g=JSON.parse(b[1].body);g.conversation_id=window.next_conversation_id?window.next_conversation_id:g.conversation_id,g.parent_message_id=window.next_parent_message_id?window.next_parent_message_id:g.parent_message_id,b[1].body=JSON.stringify(g),delete window.next_parent_message_id,delete window.next_conversation_id}else{var g=JSON.parse(b[1].body);window.conversation_id_last=g.conversation_id,window.parent_message_id_last=g.parent_message_id}}return oldFetch.apply(void 0,b)};var resizeTimer=null;window.onresize=function(){resizeTimer&&clearTimeout(resizeTimer),resizeTimer=setTimeout(function(){window.boxInit();for(var c,a=document.getElementsByTagName('button'),b=0;b<a.length;b++)c=a[b],-1!==c.innerHTML.indexOf('sidebar')&&c.addEventListener('click',function(){window.setTimeout(function(){window.boxInit()},300)})},200)},window.onresize();''')
        self.logger.debug('Sending message...')
        textbox = WebDriverWait(self.driver, 20).until(
            EC.element_to_be_clickable(chatgpt_textbox)
        )
        textbox.click()
        await asyncio.sleep(0.5)
        self.driver.execute_script(
            '''
        var element = arguments[0], txt = arguments[1];
        element.value += txt;
        element.dispatchEvent(new Event("change"));
        ''',
            textbox,
            message,
        )
        await asyncio.sleep(0.5)
        textbox.send_keys(Keys.ENTER)
        await asyncio.sleep(0.5)
        if stream:
            for i in self.__stream_message():
                print(i, end='')
                time.sleep(0.1)
            return print() # type: ignore 
        num = 5
        content = ""
        while num:
            try:
                res_code = await self.regenerate_error()
                if res_code == 0:
                    return {'message': "regenerate error! retries exceeded.", 'conversation_id': conversation_id}
                elif res_code == 2:
                    return {'message': "Sorry,please ask again.", 'conversation_id': conversation_id}
                self.logger.debug('Waiting for completion...')
                WebDriverWait(self.driver, 120).until_not(
                    EC.presence_of_element_located(chatgpt_streaming)
                )
                
                self.logger.debug('Getting response...')
                responses = self.driver.find_elements(*chatgpt_big_response)
                if responses:
                    response = responses[-1]
                    if 'text-red' in response.get_attribute('class'):
                        self.logger.debug('Response is an error')
                        raise ValueError(response.text)
                response = self.driver.find_elements(*chatgpt_small_response)[-1]

                content = markdownify(response.get_attribute('innerHTML')).replace(
                    'Copy code`', '`'
                )
                pattern = re.compile(
                    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
                )
                matches = pattern.search(self.driver.current_url)
                if not matches:
                    self.reset_conversation()
                    WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable(chatgpt_chats_list_first_node)
                    ).click()
                    matches = pattern.search(self.driver.current_url)
                conversation_id = matches.group() # type: ignore 
                break
            except:
                num -= 1
        if content[-2:] == "\n\n":
            content = content[:-2]
        return {'message': content, 'conversation_id': conversation_id}

    def reset_conversation(self) -> None:
        '''
        Reset the conversation
        '''
        
        
        if not self.driver.current_url.startswith(chatgpt_chat_url):
            return self.logger.debug('Current URL is not chat page, skipping reset')

        self.logger.debug('Resetting conversation...')
        try:
            self.driver.find_element(*chatgpt_new_chat).click()
        except SeleniumExceptions.NoSuchElementException:
            self.logger.debug('New chat button not found')
            self.driver.save_screenshot('reset_conversation_failed.png')

    def clear_conversations(self) -> None:
        '''
        Clear all conversations
        '''
        if not self.driver.current_url.startswith(chatgpt_chat_url):
            return self.logger.debug('Current URL is not chat page, skipping clear')

        self.logger.debug('Clearing conversations...')
        try:
            self.driver.find_element(*chatgpt_clear_convo).click()
        except SeleniumExceptions.NoSuchElementException:
            self.logger.debug('Clear conversations button not found')

        try:
            self.driver.find_element(*chatgpt_confirm_clear_convo).click()
        except SeleniumExceptions.NoSuchElementException:
            return self.logger.debug('Confirm clear conversations button not found')
        try:
            WebDriverWait(self.driver, 20).until_not(
                EC.presence_of_element_located(chatgpt_chats_list_first_node)
            )
            self.logger.debug('Cleared conversations')
        except SeleniumExceptions.TimeoutException:
            self.logger.debug('Clear conversations failed')

    async def refresh_chat_page(self):
        '''
        Refresh the chat page,
        and return the new conversation_id
        '''
        
        await self.cf(None)
        
        await asyncio.sleep(1)
        if not self.driver.current_url.startswith(chatgpt_chat_url):
            return self.logger.debug('Current URL is not chat page, skipping refresh')

        self.driver.get(chatgpt_chat_url)
        #self.__check_capacity(chatgpt_chat_url)
        self.__check_blocking_elements()
        
        await asyncio.sleep(0.5)
        self.logger.debug('Sending test message...')
        textbox = WebDriverWait(self.driver, 20).until(
            EC.element_to_be_clickable(chatgpt_textbox)
        )
        textbox.click()
        await asyncio.sleep(0.5)
        self.driver.execute_script(
            '''
        var element = arguments[0], txt = arguments[1];
        element.value += txt;
        element.dispatchEvent(new Event("change"));
        ''',
            textbox,
            "1",
        )
        await asyncio.sleep(0.5)
        textbox.send_keys(Keys.ENTER)
        await asyncio.sleep(0.5)

        num = 5
        while num:
            try:
                self.logger.debug('Waiting for completion...')
                WebDriverWait(self.driver, 120).until_not(
                    EC.presence_of_element_located(chatgpt_streaming)
                )
                
                self.logger.debug('Getting response...')
                responses = self.driver.find_elements(*chatgpt_big_response)
                if responses:
                    response = responses[-1]
                    if 'text-red' in response.get_attribute('class'):
                        self.logger.debug('Response is an error')
                        raise ValueError(response.text)
                response = self.driver.find_elements(*chatgpt_small_response)[-1]

                break
            except:
                num -= 1
        await asyncio.sleep(0.5)
        return await self.return_chat_url()
        
    async def backtrack_chat(self,loop_text:str,conversation_id: str = "") -> dict:
        '''
        backtrack the chat,
        conversation_id : conversation_id,
        loop_text: history messages you have sent in this conversation,
        return bool
        '''
        if conversation_id == "":
            conversation_id = self.__conversation_id
            
        await self.cf(conversation_id)
        
        self.driver.get(self.driver.current_url)
        self.logger.debug('Find loop...')
        self.__check_blocking_elements()
        
        await asyncio.sleep(2)
        
        loop_text_num = ""
        chatgpt_loop_text = self.driver.find_elements(By.XPATH,"//div[@class='min-h-[20px] flex flex-col items-start gap-4 whitespace-pre-wrap']")
        for x,y in enumerate(chatgpt_loop_text[::-1]):
            if loop_text in y.text:
                loop_text_num = str(len(chatgpt_loop_text) - x)
        self.logger.debug('Waiting for backtrack...')
        
        chatgpt_loop_button_on_text_find = '//*[@id="__next"]/div[2]/div/main/div[1]/div/div/div/div['+ loop_text_num + ']/div/div[2]/div[2]'
        chatgpt_loop_button_submit_text = '//*[@id="__next"]/div[2]/div/main/div[1]/div/div/div/div['+ loop_text_num + ']/div/div[2]/div[1]/div/button[1]'
        
        self.logger.debug('Refresh chat page...')
        
        chatgpt_loop_button_on_find = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, chatgpt_loop_button_on_text_find))
        ) 
        try:
            chatgpt_loop_button_on_find.click()
        except:
            pass
        try:
            chatgpt_loop_button_submit = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH,chatgpt_loop_button_submit_text))
            )  
            
            chatgpt_loop_button_submit.click()
        except:
            return {"status":False}
            #pass
        self.logger.debug('Waiting for completion...')
        WebDriverWait(self.driver, 120).until_not(
            EC.presence_of_element_located(chatgpt_streaming)
        )

        self.logger.debug('Getting response...')
        responses = self.driver.find_elements(*chatgpt_big_response)
        if responses:
            response = responses[-1]
            if 'text-red' in response.get_attribute('class'):
                self.logger.debug('Response is an error')
                raise ValueError(response.text)
        response = self.driver.find_elements(*chatgpt_small_response)[-1]
        if response:
            return {"status":True}
        else:
            return {"status":False}
        
    async def init_personality(self,new_conversation:bool=True, conversation_id = "",personality_definition:list=[]) -> dict:
        '''
        new_conversation : Whether to open a new session for personality initialization, the default is true
        
        personality_definition: Personality initialization phrase is a list, a single element is a dict, 
        content is the content of the phrase, and AI_verify is a successful detection of personality
        
        returns a dict,boolean result and the conversation_id in it.
        '''
        
        
        if new_conversation:
            new_conversation_id = await self.refresh_chat_page()
            conversation_id = new_conversation_id
        try:
            if not personality_definition:
                personality_definition = self.__personality_definition
                
            for single_definition in personality_definition:
                this_res = await self.send_message(conversation_id,single_definition["content"]) # type: ignore
                await asyncio.sleep(1)
                if single_definition["AI_verify"]:
                    this_status = self.wide_awake(this_res["message"])
                    error_num = 0
                    while this_status:
                        await self.backtrack_chat(conversation_id,single_definition["content"]) # type: ignore
                        await asyncio.sleep(1)
                        responses = self.driver.find_elements(*chatgpt_big_response)
                        if responses:
                            response = responses[-1]
                            if 'text-red' in response.get_attribute('class'):
                                self.logger.debug('Response is an error')
                                raise ValueError(response.text)
                        response = self.driver.find_elements(*chatgpt_small_response)[-1]
                        content = markdownify(response.get_attribute('innerHTML')).replace('Copy code`', '`')
                        if content[-2:] == "\n\n":
                            content = content[:-2]
                        this_status = self.wide_awake(content)
                        error_num += 1
                        if error_num > 3:
                            '''
                            If it fails more than three times, there may be a problem with your initialization vocabulary
                            '''
                            break
                        
                        
            res = await self.send_message(conversation_id,"so please introduce yourself now")  # type: ignore
            status = self.wide_awake(res["message"])
            if status :
                status = False
            else:
                status = True        
            return {"status":status,"conversation_id":conversation_id}
        except:
            return {"status":False,"conversation_id":conversation_id}
        
    def wide_awake(self,res:str) -> bool:
        '''AI tag'''
        words = ["AI","Ai","ai","Assistant","language model","OpenAI","程序","计算机","人工智能","机器人"]
        #Initialization result detection vocabulary, which can be changed according to its own language and initialization statement
        
        status = False
        for word in words:
            if word in res:
                status = True
        return status
    
    async def cf(self,conversation_id) -> None:
        '''A new way to verify cf'''
        if not conversation_id:
            conversation_id = self.__conversation_id
        self.logger.debug('Ensuring Cloudflare cookies...')
        await self.__ensure_cf()

        self.logger.debug('Opening chat page...')
        self.driver.get(f'{chatgpt_chat_url}/{conversation_id}')
        self.__check_blocking_elements()
        
        
        # self.logger.debug('Ensuring Cloudflare cookies...')
        # await self.__ensure_cf()
        # self.driver.get(f'{chatgpt_chat_url}/{conversation_id}')
        # self.__check_blocking_elements()
    
    async def return_chat_url(self):
        '''
        open new tab,and return the new conversation_id'''
        
        self.logger.debug('Opening new tab...')
        original_window = self.driver.current_window_handle
        self.driver.switch_to.new_window('tab')
        num = 5
        conversation_id = ""
        while num:
            try:
                self.driver.get("https://chat.openai.com/api/auth/session")
                await asyncio.sleep(2)
                token = "Bearer "
                Authorization = []
                try:
                    response = self.driver.execute_script("return JSON.parse(document.body.innerText)")
                    token += response["accessToken"]
                    Authorization.append(token)
                except:
                    pass
                headers = {'Authorization': token} 
                self.driver.execute_cdp_cmd("Network.enable", {})   
                self.driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {'headers': headers})
                self.driver.get("https://chat.openai.com/backend-api/conversations?offset=0&limit=1")
                await asyncio.sleep(2)
                
                page_json = self.driver.execute_script("return JSON.parse(document.body.innerText)")
                conversation_id = page_json["items"][0]["id"]
                
                self.logger.debug('Closing tab...')
                self.driver.close()
                self.driver.switch_to.window(original_window)
                break
            except:
                num -= 1
 
        return conversation_id
        
    async def loop_gpt(self):
        '''
        Handle event loop messages
        
        
        self.rec :  return message
        '''
        while 1:
            await asyncio.sleep(0.5)
            if not self.send_queue.empty():
                msg_send = await self.send_queue.get()
                if msg_send["type"] == "msg":
                    # msg 
                    try:
                        msg_rec = await self.send_message(msg_send["conversation_id"],msg_send["msg"])
                    except:
                        msg_send["msg_rec"] = {}
                        msg_send["msg_rec"]["message"] = "猪咪不知道..."
                        msg_rec = msg_send["msg_rec"]
                        
                    if msg_rec:
                        msg_send["msg_rec"] = msg_rec
                        
                        # Do other processing on the reply
                        # if msg_send["tts"]:
                        #     self.tts_queue.put_nowait(msg_send)
                        
                elif msg_send["type"] == "loop":
                    try:
                        msg_send["msg_rec"] = await self.backtrack_chat(msg_send["msg"],msg_send["conversation_id"])
                    except:
                        
                        msg_send["msg_rec"] = {"status":False}
                elif msg_send["type"] == "init":
                    try:
                        msg_send["msg_rec"] = await self.init_personality(bool(msg_send["msg"]),msg_send["conversation_id"])
                    except:
                        
                        msg_send["msg_rec"] = {"status":False,"conversation_id":""}
                
                elif msg_send["type"] == "update_cookie":
                    try:
                        msg_send["msg_rec"] = await self.update_cookie(msg_send["msg"])
                    except:
                        msg_send["msg_rec"] = {"status":False}
                    
                self.rec.append(msg_send)
    
    async def get_id(self) -> int:
        ''' msg id '''
        self.msg_id += 1
        return self.msg_id
                
    async def async_send_message(self,msg,conversation_id:str = "",msg_type: str = "msg") -> dict:
        '''async send_message,
        conversation_id: conversation_id,
        msg: your message to gpt.
        returns a dictionary containing the conversation id and the reply
        '''
        if conversation_id == "":
            conversation_id = self.__conversation_id
            
        msg_dict = {
            "id":await self.get_id(), 
            "type":msg_type,
            "msg":msg,
            "conversation_id":conversation_id
        }
        await self.send_queue.put(msg_dict)
        
        rec_lock = False
        message :dict 
        while 1:
            for x in self.rec:
                if x["id"] == msg_dict["id"]:
                    rec_lock = True
                    message = x["msg_rec"]
                    self.rec.remove(x)
                    break
            if rec_lock:
                break
            await asyncio.sleep(2)
            
        return message   # type: ignore
    
    async def regenerate_error(self):
        '''gpt reply error handling,
return 0 means processing failed,
return 1 means no error occurred,
return 2 means that an error occurred but the processing was successful, 
and returning to the previous dialogue'''
        while_num = 5
        while while_num:
            responses = self.driver.find_elements(By.XPATH, '//*[@id="__next"]/div[2]/div/main/div[2]/form/div/div/span') 
            if responses:
                while_num -= 1
                self.logger.debug('Waiting for regenerat error...')
                response = responses[-1]
                chatgpt_loop_text = self.driver.find_elements(By.XPATH,"//div[@class='min-h-[20px] flex flex-col items-start gap-4 whitespace-pre-wrap']")
                loop_text_num = str(len(chatgpt_loop_text) + 1)
                chatgpt_loop_button_on_text_find = '//*[@id="__next"]/div[2]/div/main/div[1]/div/div/div/div['+ loop_text_num + ']/div/div[2]/div[2]'
                chatgpt_text_ok = '//*[@id="__next"]/div[2]/div/main/div[1]/div/div/div/div['+ loop_text_num + ']/div/div[2]/div[1]/textarea'
                chatgpt_loop_button_submit_text = '//*[@id="__next"]/div[2]/div/main/div[1]/div/div/div/div['+ loop_text_num + ']/div/div[2]/div[1]/div/button[1]'
                chatgpt_loop_button_on_find = WebDriverWait(self.driver, 10).until(
                    EC.visibility_of_element_located((By.XPATH, chatgpt_loop_button_on_text_find))
                ) 
                try:
                    chatgpt_loop_button_on_find.click()
                except:
                    pass
                try:
                    chatgpt_text_ok_textbox = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH,chatgpt_text_ok))
                    ) 
                    chatgpt_text_ok_textbox.clear()
                    chatgpt_text_ok_textbox.send_keys("ok")
                    
                    chatgpt_loop_button_submit = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH,chatgpt_loop_button_submit_text))
                    )  
                    
                    chatgpt_loop_button_submit.click()
                except:
                    pass
                self.logger.debug('Waiting for completion...')
                WebDriverWait(self.driver, 10).until_not(
                    EC.presence_of_element_located(chatgpt_streaming)
                )
                await asyncio.sleep(2)
            else:
                if while_num == 5:
                    return 1
                else:
                    return 2
        return 0
    
    async def update_cookie(self,cookie_value: str) -> dict:
        '''update your new session_token'''
        try:
            cookie_dict = self.driver.get_cookies()
            for cookie in cookie_dict:
                if cookie['name'] == "__Secure-next-auth.session-token":
                    cookie['value'] = cookie_value
            for cookie in cookie_dict:
                self.driver.add_cookie(cookie)
            return {"status":True}
        except:
            return {"status":False}