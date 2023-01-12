from pyChatGPTLoop import ChatGPT
import os


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


if __name__ == '__main__':
    while True:
        session_token = input('Please enter your session token: ')
        
        conversation_id = input(
            'Please enter your conversation id (if you want to continue old chat): '
        )
        
        proxy = input('Please enter your proxy if you have: eg: http://127.0.0.1:8080')
        
        driver_path = input('Please enter your chromedriver path if you have: eg: D:\\chromedriver.exe')
        
        chat = ChatGPT(session_token, conversation_id,proxy=proxy,driver_path=driver_path)
        break

    clear_screen()
    print(
        'Conversation started. Type "reset" to reset the conversation.Type "back some words" to loop the conversation. Type "quit" to quit.\n'
    )
    words = [
        {
            "content":r'Now you are going to pretend to be a math teacher called "nothing" to help me with my math',
            "AI_verify":True
            },
        {
            "content":r"You will be very strict in pointing out my mistakes",
            "AI_verify":False
            }
    ]
    '''
    An example of initializing the vocabulary format, the vocabulary content is not representative
    '''
    
    while True:
        prompt = input('\nYou: ')
        if prompt.lower() == 'reset':
            chat.reset_conversation()
            #clear_screen()
            print(
                'Conversation started. Type "reset" to reset the conversation. Type "back some words" to loop the conversation.Type "quit" to quit.\n'
            )
            
        elif prompt.lower().split(' ')[0] == 'back':
            
            print('\nChatGPT: ', end='')
            loop_text = prompt.lower().split('back')[1][1:]
            response = chat.backtrack_chat(loop_text)
            if response:
                print("yes!", end='')
            else:
                print("error!", end='')
                
        elif prompt.lower() == 'quit':
            break
        
        elif prompt.lower() == "new":
            res = chat.init_personality(True,words)
            if res:
                print("yes!")
            else:
                print("no!")
                
        else:
            print('\nChatGPT: ', end='')
            response = chat.send_message(prompt)
            print(response['message'], end='')
