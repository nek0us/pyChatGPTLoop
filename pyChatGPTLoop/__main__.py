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
        proxy = input('Please enter your proxy: ')
        
        chat = ChatGPT(session_token, conversation_id,proxy=proxy)
        break

    clear_screen()
    print(
        'Conversation started. Type "reset" to reset the conversation.Type "back some words" to loop the conversation. Type "quit" to quit.\n'
    )
    while True:
        prompt = input('\nYou: ')
        if prompt.lower() == 'reset':
            chat.reset_conversation()
            #clear_screen()
            print(
                'Conversation started. Type "reset" to reset the conversation. Type "back some words" to loop the conversation.Type "quit" to quit.\n'
            )
            continue
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
        else:
            print('\nChatGPT: ', end='')
            response = chat.send_message(prompt)
            print(response['message'], end='')
