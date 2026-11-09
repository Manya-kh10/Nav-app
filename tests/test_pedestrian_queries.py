import pytest
from app.services.intent.classifier import classify

@pytest.mark.parametrize("text,expected_intent", [
    # time_left
    ('और कितना चलना है मुझे?', 'time_left'),
    ('और कितना चलना है', 'time_left'),
    ('और कितना time लगेगा?', 'time_left'),
    ('और कितना समय लगेगा?', 'time_left'),
    ('aur kitna chalna hai mujhe', 'time_left'),
    ('aur kitna time lagega', 'time_left'),
    ('kitna chalna padega mujhe', 'time_left'),
    ('abhi aur kitani there chalana hai', 'time_left'),
    ('how long do i have to walk', 'time_left'),
    ('how much time is left', 'time_left'),
    ('how many minutes left', 'time_left'),
    ('how long will it take', 'time_left'),
    # distance_left
    ('और कितना दूर है?', 'distance_left'),
    ('कितनी दूर और चलना है?', 'distance_left'),
    ('aur kitni door hai', 'distance_left'),
    ('how far is my destination', 'distance_left'),
    ('how many meters left', 'distance_left'),
    ('how many km left', 'distance_left'),
    # next_turn
    ('अब मैं कहाँ जाऊँ?', 'next_turn'),
    ('अब मैं कहां जाऊं?', 'next_turn'),
    ('अब किधर जाना है?', 'next_turn'),
    ('कहाँ जाना है?', 'next_turn'),
    ('किधर जाना है?', 'next_turn'),
    ('ab main kahan jaun', 'next_turn'),
    ('ab kidhar jana hai', 'next_turn'),
    ('where should i go next', 'next_turn'),
    ('where do i go now', 'next_turn'),
    ('which turn should i take', 'next_turn'),
    ('which road to take', 'next_turn'),
    ('which way should i go', 'next_turn'),
    ('what next', 'next_turn'),
    ('next turn', 'next_turn'),
    ('अगला मोड़ कौन सा है?', 'next_turn'),
    ('आगे कहाँ मुड़ना है?', 'next_turn'),
    # on_route
    ('क्या यह turn सही है?', 'on_route'),
    ('क्या यह मोड़ सही है?', 'on_route'),
    ('क्या मैं सही रास्ते पर हूँ?', 'on_route'),
    ('kya yeh turn sahi hai', 'on_route'),
    ('is this the right turn', 'on_route'),
    ('did i take the right turn', 'on_route'),
    ('am i on the right track', 'on_route'),
    ('am i going the right way', 'on_route'),
    ('am i on the right route', 'on_route'),
    ('am i lost', 'on_route'),
    ('wrong way', 'on_route'),
    # arrived_check
    ('have i arrived', 'arrived_check'),
    ('did i reach', 'arrived_check'),
    ('क्या हम पहुँच गए?', 'arrived_check'),
    ('pahunch gaye kya', 'arrived_check'),
    # repeat
    ('say that again', 'repeat'),
    ('फिर से बोलो', 'repeat'),
    ('dobara batao', 'repeat'),
    # start_navigation
    ('start walking', 'start_navigation'),
    ('चलना शुरू करो', 'start_navigation'),
    ('shuru karo', 'start_navigation'),
])
def test_pedestrian_queries(text, expected_intent):
    intent, lang = classify(text)
    assert intent == expected_intent, f"Failed for '{text}': got {intent}, expected {expected_intent}"

