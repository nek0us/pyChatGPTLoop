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
        driver_path = '',
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
        self.loop = asyncio.get_event_loop()
        self.t2 = asyncio.ensure_future(self.loop_gpt())
        self.t = threading.Thread(target=self.loop.run_forever)
        self.t.start()
        
        asyncio.run(self.__init_browser())
        
        
        

    def __del__(self):
        '''
        Close the browser and display
        '''
        self.loop.stop()
        
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

    async def __ensure_cf(self, retry: int = 3) -> None:
        '''
        Ensure Cloudflare cookies are set\n
        :param retry: Number of retries
        '''
        self.logger.debug('Opening new tab...')
        original_window = self.driver.current_window_handle
        self.driver.switch_to.new_window('tab')

        self.logger.debug('Getting Cloudflare challenge...')
        self.driver.get('https://chat.openai.com/api/auth/session')
        try:
            
            page  = self.driver.execute_script("return JSON.parse(document.body.innerText)")
            response = json.dumps(self.driver.execute_script("return JSON.parse(document.body.innerText)"))
            
        except:
            # cf 
            try:
                # cf button
                cf_button = False
                try:
                    cf_button_find = WebDriverWait(self.driver, 10).until(
                    EC.visibility_of_element_located((By.XPATH, '//*[@id="challenge-stage"]/div/input'))
                ) 
                    cf_button = True
                except:
                    pass
                
                if cf_button:
                
                    cf_button_find = WebDriverWait(self.driver, 10).until(
                    EC.visibility_of_element_located((By.XPATH, '//*[@id="challenge-stage"]/div'))
                ) 
                    cf_button_find.click()
                    
                else:
                    self.logger.debug(f'Cloudflare challenge failed, retrying {retry}...')
                    self.driver.save_screenshot(f'cf_failed_{retry}.png')
                    if retry > 0:
                        self.logger.debug('Closing tab...')
                        self.driver.close()
                        self.driver.switch_to.window(original_window)
                        return await self.__ensure_cf(retry - 1)
                    raise ValueError('Cloudflare challenge failed')
                
                
            except SeleniumExceptions.TimeoutException:
                
                self.logger.debug(f'Cloudflare challenge failed, retrying {retry}...')
                self.driver.save_screenshot(f'cf_failed_{retry}.png')
                if retry > 0:
                    self.logger.debug('Closing tab...')
                    self.driver.close()
                    self.driver.switch_to.window(original_window)
                    return await self.__ensure_cf(retry - 1)
                raise ValueError('Cloudflare challenge failed')
        self.logger.debug('Cloudflare challenge passed')
        
        self.driver.get('https://chat.openai.com/api/auth/session')
        wait = WebDriverWait(self.driver, 5).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, 'a')))
        await asyncio.sleep(3)
        self.logger.debug('Validating authorization...')
        try:
            response = json.dumps(self.driver.execute_script("return JSON.parse(document.body.innerText)"))
        
        except:
            await asyncio.sleep(3)
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

        await asyncio.sleep(2)
        
        self.logger.debug('Sending message...')
        textbox = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable(chatgpt_textbox)
        )
        textbox.click()
        self.driver.execute_script(
            '''
        var element = arguments[0], txt = arguments[1];
        element.value += txt;
        element.dispatchEvent(new Event("change"));
        ''',
            textbox,
            message,
        )
        textbox.send_keys(Keys.ENTER)

        if stream:
            for i in self.__stream_message():
                print(i, end='')
                time.sleep(0.1)
            return print() # type: ignore 

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
        
        
        if not self.driver.current_url.startswith(chatgpt_chat_url):
            return self.logger.debug('Current URL is not chat page, skipping refresh')

        self.driver.get(chatgpt_chat_url)
        self.__check_capacity(chatgpt_chat_url)
        self.__check_blocking_elements()
        
        
        self.logger.debug('Sending test message...')
        textbox = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable(chatgpt_textbox)
        )
        textbox.click()
        self.driver.execute_script(
            '''
        var element = arguments[0], txt = arguments[1];
        element.value += txt;
        element.dispatchEvent(new Event("change"));
        ''',
            textbox,
            "1",
        )
        textbox.send_keys(Keys.ENTER)


        self.logger.debug('Waiting for completion...')
        WebDriverWait(self.driver, 120).until_not(
            EC.presence_of_element_located(chatgpt_streaming)
        )

        return await self.return_chat_url()
        
    async def backtrack_chat(self,loop_text:str,conversation_id: str = "") -> bool:
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
            return False
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
            return True
        else:
            return False
        
    async def init_personality(self,new_conversation:bool=True, conversation_id = "",personality_definition:list=[{"content":"you are a pig","AI_verify":True}]) -> dict:
        '''
        new_conversation : Whether to open a new session for personality initialization, the default is true
        
        personality_definition: Personality initialization phrase is a list, a single element is a dict, 
        content is the content of the phrase, and AI_verify is a successful detection of personality
        
        returns a dict,boolean result and the conversation_id in it.
        '''
        
        
        if new_conversation:
            new_conversation_id = await self.refresh_chat_page()
            conversation_id = new_conversation_id
        
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
                
        return {"status":status,"conversation_id":conversation_id}
        
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
        
        
        self.logger.debug('Ensuring Cloudflare cookies...')
        await self.__ensure_cf()
        self.driver.get(f'{chatgpt_chat_url}/{conversation_id}')
        self.__check_blocking_elements()
    
    async def return_chat_url(self):
        '''
        open new tab,and return the new conversation_id'''
        
        self.logger.debug('Opening new tab...')
        original_window = self.driver.current_window_handle
        self.driver.switch_to.new_window('tab')
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
 
        return conversation_id
        
    async def loop_gpt(self):
        '''
        Handle event loop messages
        
        
        self.rec :  return message
        '''
        while True:
            await asyncio.sleep(4)
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
                        msg_send["msg_rec"] = await self.backtrack_chat(msg_send["msg_send"],msg_send["conversation_id"])
                    except:
                        
                        msg_send["msg_rec"] = False
                elif msg_send["type"] == "init":
                    try:
                        msg_send["msg_rec"] = await self.init_personality(bool(msg_send["msg_send"]),msg_send["conversation_id"])
                    except:
                        
                        msg_send["msg_rec"] = {"status":False,"conversation_id":""}
                    
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