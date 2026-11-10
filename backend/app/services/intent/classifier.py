import re

from rapidfuzz import fuzz

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_KANNADA = re.compile(r"[\u0C80-\u0CFF]")
_LATIN = re.compile(r"[a-zA-Z]")

FUZZY_MIN_LEN = 10   # only phrases at least this long get typo tolerance
FUZZY_SCORE = 90


def _collapse(s: str) -> str:
    """Collapse repeated letters so spelling variants match (kahaan = kahan, theek = thek)."""
    return re.sub(r"(\w)\1+", r"\1", s)


def _norm(text: str) -> str:
    return _collapse(re.sub(r"[^\w\u0900-\u097F\u0C80-\u0CFF]+", " ", text.lower()).strip())


def _s(*words: str) -> set[str]:
    return {_collapse(w) for w in words}


_HINGLISH = _s(
    "kya", "mujhe", "kahan", "kaha", "kidhar", "kitna", "kitni", "kitne", "kitani", "mudna", "modna",
    "mudun", "sahi", "galat", "raste", "rasta", "hoon", "hun", "hu", "hai", "ab", "abhi", "lagega",
    "lagegi", "kab", "aap", "mera", "samay", "phir", "dobara", "bolo", "batao", "bataiye",
    "agla", "pahunch", "rahi", "raha", "theek", "jana", "jaun", "hum", "gaye", "gaya", "gayi",
    "lena", "chalna", "chalana", "chalo", "shuru", "padega", "padegi", "paidal", "aur", "manzil", "aage", "band", "halka", "dhoond",
    "bache", "bacha", "jaana", "jaoon", "jaon", "kaun", "kaunsa", "sa", "yeh", "ye", "woh", "wo", "kidr", "nahi", "toh",
    "door", "dur", "bhatak",
)

_KANGLISH = _s(
    "munde", "elli", "tiruga", "tirugabeku", "thiruga", "thirugbeku", "tirugi", "thirugi",
    "tirugli", "thirugli", "yava", "kade", "doora", "eshtu", "eshtide", "eshtidhe", "hottu",
    "samaya", "nimisha", "dari", "daari", "dhaari", "darina", "dharina", "sari", "sariyada", "tappu",
    "talupiddheva", "talupidheva", "talupidena", "talupidva", "bantha", "banta", "matte", "heli",
    "hogabeku", "hogbeku", "hogtiddiva", "hogtiddeeva", "hogthiddeeva", "hogthiddiva", "muttidheva",
    "innomme", "innondhu", "hegide", "hegidhe", "ideya", "idheya", "tada", "edakke", "edakkey",
    "balakke", "balakkey", "neravagi", "aaytha", "aytha", "aagidhe", "aagatte", "agatte",
    "aagidiya", "aagidheya", "agidiya", "agidheya",
    "apaghata", "apaghatha", "yenadru", "enadru", "jaasti",
    "nadeyabeku", "nadibeku", "prarambhisi", "hogona",
)

# order matters: first matching intent wins
RULES = [
    ("start_navigation", [
        "start", "start walking", "start walk", "start navigation", "start the walk", "start route",
        "let's go", "lets go", "begin walk", "begin",
        "shuru karo", "chalna shuru", "chalo", "shuru", "shuru karein", "chalna shuru karein",
        "शुरू करो", "चलना शुरू", "चलो", "शुरू करें",
        "ಪ್ರಾರಂಭಿಸಿ", "ಶುರು ಮಾಡಿ", "ಹೋಗೋಣ", "ನಡೆಯಲು ಪ್ರಾರಂಭಿಸಿ",
        "prārambhisi", "prarambhisi", "shuru maadi", "shuru madi", "hogona", "walk shuru",
    ]),
    ("repeat", [
        "repeat", "say that again", "say again", "once more", "again", "what did you say",
        "dobara", "phir se", "ek baar aur", "repeat karo", "फिर से", "दोबारा", "दुबारा",
        "ಮತ್ತೆ ಹೇಳಿ", "ಇನ್ನೊಮ್ಮೆ ಹೇಳಿ", "ಮತ್ತೊಮ್ಮೆ ಹೇಳಿ", "ಏನ್ ಹೇಳಿದ್ರಿ", "ಏನು ಹೇಳಿದ್ರಿ", "ಇನ್ನೊಂದು ಸಲ ಹೇಳಿ",
        "matte heli", "innomme heli", "innondhu sala heli", "en helidri", "yen helidri",
    ]),
    ("incident", [
        "any incident", "any accidents", "any accident", "any crash", "road closed", "road blocked",
        "road works", "construction ahead", "accident ahead", "jam ahead",
        "koi accident", "accident hua hai kya", "road band hai kya", "koi jam hai kya",
        "koi incident", "traffic jam ahead", "aage koi jam",
        "ಯಾವುದಾದರೂ ಅಪಘಾತ", "ರಸ್ತೆ ಬಂದ್ ಆಗಿದೆಯಾ", "ಅಪಘಾತವಾಗಿದೆಯಾ", "ಯಾವುದಾದರೂ ಜಾಮ್ ಇದೆಯಾ", "ಅಪಘಾತ ಏನಾದರೂ ಇದೆಯಾ", "ರಸ್ತೆ ಬ್ಲಾಕ್ ಆಗಿದೆಯಾ",
        "accident aagidiya", "accident aagidheya", "raste band agidiya", "raste block aagidiya", "enadru accident", "yenadru accident",
    ]),
    ("delay", [
        "how much delay", "traffic delay", "any delay", "is there any delay", "how late",
        "kitna delay", "delay kitna hai", "kitna der hoga", "traffic delay kitna hai",
        "कितना डिले", "कितना लेट", "कितनी देरी",
        "ಎಷ್ಟು ತಡ", "ಎಷ್ಟು ಡಿಲೇ", "ಡಿಲೇ ಎಷ್ಟಿದೆ", "ತಡವಾಗುತ್ತಾ", "ಎಷ್ಟು ಲೇಟ್ ಆಗುತ್ತೆ", "ತಡ ಎಷ್ಟು",
        "eshtu delay", "eshtu tada", "delay eshtide", "eshtu late aagatte", "tada aagatta",
    ]),
    ("traffic_ahead", [
        "how is the traffic", "how is traffic", "is there traffic", "traffic condition",
        "traffic ahead", "any traffic", "traffic update", "traffic report", "is traffic heavy",
        "traffic kaisa hai", "aage traffic kaisa hai", "traffic kaisa", "aage traffic hai kya",
        "traffic hai kya", "kitna traffic hai", "traffic kaisa h", "ट्रैफिक कैसा है", "आगे ट्रैफिक कैसा है",
        "ಟ್ರಾಫಿಕ್ ಹೇಗಿದೆ", "ಟ್ರಾಫಿಕ್ ಇದೆಯಾ", "ಮುಂದೆ ಟ್ರಾಫಿಕ್ ಇದೆಯಾ", "ಟ್ರಾಫಿಕ್ ಪರಿಸ್ಥಿತಿ ಏನು", "ರಸ್ತೆಯಲ್ಲಿ ಟ್ರಾಫಿಕ್ ಹೇಗಿದೆ",
        "traffic hegide", "traffic hegidhe", "traffic ideya", "munde traffic ideya", "aage traffic hegide", "traffic jaasti ideya",
    ]),
    ("arrived_check", [
        "have i arrived", "have we arrived", "did i arrive", "did we arrive",
        "did i reach", "did we reach", "have i reached", "have we reached", "are we there", "am i there", "are we there yet",
        "did i reach destination", "did i reach the destination", "have i reached destination",
        "pahunch gaye", "pahunch gaya", "pahunch gayi", "pahunch gye", "reach gaye",
        "reach gaya", "reach gayi", "manzil aa gayi", "manzil aa gaya", "manzil pahunch",
        "pahunch gaye kya", "reach gaye kya", "kya hum pahunch gaye", "kya main pahunch gaya",
        "पहुँच गए", "पहुंच गए", "पहुँच गया", "पहुंच गया", "क्या हम पहुँच गए", "क्या हम पहुंच गए",
        "क्या मैं पहुँच गया", "क्या मैं पहुंच गया", "पहुँच गए क्या", "पहुंच गए क्या", "मंज़िल आ गई क्या", "मंजिल आ गई क्या",
        "ತಲುಪಿದ್ದೇವಾ", "ತಲುಪಿದೆವಾ", "ಮುಟ್ಟಿದ್ದೇವಾ", "ತಲುಪಿದಿವಾ", "ಬಂತಾ", "ಜಾಗ ಬಂತಾ", "ನಾವು ತಲುಪಿದ್ದೇವಾ", "ರೀಚ್ ಆಯ್ತಾ",
        "talupiddheva", "talupidheva", "bantha", "jaaga bantha", "reach aaytha", "reach aytha", "reach aagidheeva",
    ]),
    ("on_route", [
        "right track", "right path", "right route", "right way", "right direction",
        "is this the right turn", "is this turn right", "is this the correct turn",
        "did i turn correctly", "did i take the right turn", "did i make the right turn",
        "is that the right turn", "correct turn", "right turn",
        "correct way", "correct route", "on route", "on the route", "on track", "am i lost",
        "wrong way", "wrong turn", "going the right way", "did i miss the turn", "did i miss my turn",
        "am i on the right track", "am i on the right path", "am i going the right way", "am i on route",
        "sahi raste", "sahi rasta", "sahi route", "sahi disha", "sahi direction", "sahi ja",
        "sahi jaa", "theek raste", "theek ja", "galat raste", "galat rasta", "galat ja",
        "kya yeh turn sahi hai", "kya ye turn sahi hai", "turn sahi hai", "sahi turn hai",
        "sahi mod hai", "kya main sahi ja raha hoon", "kya main sahi ja raha hu", "kya hum sahi raste par hain",
        "kya main sahi ja rahi hoon", "kya me sahi ja rahi hu", "sahi ja rahi hu", "sahi ja rahi hu kya",
        "sahi ja raha hu", "sahi ja rahe hai na", "sahi ja rahi hu na", "sahi ja raha hu na",
        "sahi raste pe hu na", "sahi raste par hu na", "sahi raste pe ja rahe hai", "sahi raste pe hu kya",
        "rasta theek hai na", "rasta sahi hai na", "rasta theek hai kya", "rasta sahi hai kya",
        "galat raste toh nahi", "galat raste to nahi aa gaye", "galat to nahi ja rahe", "galat toh nahi ja rahe", "galat direction",
        "kya main rasta bhatak gaya", "rasta bhatak gaye kya", "rasta bhatak gaya kya", "bhatak to nahi gaye", "bhatak toh nahi gaye",
        "main bhatak to nahi gaya", "main bhatak to nahi gayi", "mai bhatak to nahi gaya", "mai bhatak to nahi gayi",
        "yahi rasta hai kya", "yahi rasta hai na", "idhar hi jana hai kya", "yahin se jana hai kya", "idhar se hi jana hai kya",
        "sahi disha me hu na", "sahi chal rahe hai na",
        "क्या यह turn सही है", "क्या ये turn सही है", "क्या यह टर्न सही है", "क्या यह मोड़ सही है", "क्या ये मोड़ सही है",
        "टर्न सही है क्या", "सही मोड़ है क्या", "सही टर्न है क्या", "क्या मैं सही दिशा में हूँ", "क्या मैं सही दिशा में हूं",
        "क्या मैं सही रास्ते पर हूँ", "क्या मैं सही रास्ते पर हूं", "सही रास्ता है क्या", "क्या यह सही रास्ता है", "क्या हम सही जा रहे हैं",
        "क्या मैं सही जा रही हूँ", "क्या मैं सही जा रहा हूँ", "सही जा रही हूँ क्या", "सही जा रहा हूँ क्या", "सही जा रहे हैं क्या",
        "सही जा रही हूँ", "सही जा रहा हूँ", "सही जा रहे हैं ना", "सही जा रही हूँ ना", "सही जा रहा हूँ ना",
        "सही रास्ते पे हूँ ना", "सही रास्ते पर हूँ ना", "सही रास्ते पे जा रहे हैं", "सही रास्ते पर जा रहे हैं",
        "रास्ता ठीक है ना", "रास्ता सही है ना", "रास्ता ठीक है क्या", "रास्ता सही है क्या",
        "गलत तो नहीं जा रहे", "गलत तो नहीं जा रही", "गलत तो नहीं जा रहा", "गलत रास्ते तो नहीं आ गए", "गलत रास्ते पे तो नहीं आ गए",
        "भटक तो नहीं गए", "रास्ता भटक गए क्या", "रास्ता भटक गया क्या", "मैं भटक तो नहीं गया", "मैं भटक तो नहीं गई",
        "यही रास्ता है क्या", "यही रास्ता है ना", "इधर ही जाना है क्या", "यहीं से जाना है क्या", "इधर से ही जाना है क्या",
        "सही दिशा में हूँ ना", "सही दिशा में जा रहे हैं", "सही दिशा है क्या", "सही चल रहे हैं ना",
        "सही रास्ते", "सही रास्ता", "सही जा", "गलत रास्ते", "गलत रास्ता", "क्या मैं रास्ता भटक गया",
        "ಸರಿಯಾದ ದಾರಿ", "ಸರಿ ದಾರಿ", "ಸರಿಯಾದ ಮಾರ್ಗ", "ಸರಿ ದಾರಿನಾ", "ತಪ್ಪು ದಾರಿ", "ಸರಿಯಾಗಿ ಹೋಗ್ತಿದ್ದೀವಾ", "ಸರಿ ಹೋಗ್ತಿದ್ದೀವಾ",
        "ನಾವು ಸರಿಯಾದ ದಾರಿಯಲ್ಲಿದ್ದೇವಾ", "ನಾವು ಸರಿ ಹೋಗ್ತಿದ್ದೀವಾ", "ನಾನು ಸರಿಯಾಗಿ ಹೋಗ್ತಿದ್ದೀನಾ", "ದಾರಿ ತಪ್ಪಿದ್ದೇವಾ", "ತಪ್ಪು ದಾರಿಗೆ ಬಂದ್ವಾ", "ದಾರಿ ಸರಿ ಇದೆಯಾ", "ಇದೇ ದಾರಿನಾ", "ಸರಿ ದಾರಿನಾ",
        "sariyada dari", "sari dari", "tappu dari", "sariyada marga", "sari hogtiddeeva", "sari hogtiddiva", "sariyagi hogtiddiva", "sari hogtha iddeeva",
        "sariyada dariyalliddeva", "sari hogtiddini", "dari tappiddheva", "tappu darige bandva", "dari sari ideya", "ide darina", "dari thappidheya",
    ]),
    ("time_left", [
        "how long", "how much time", "time left", "minutes left", "how many minutes", "how many minutes left", "eta",
        "when will i reach", "when do i arrive", "how long will it take", "kitna time", "kitni der", "kitna samay",
        "kab tak", "kab pahunch", "कितना समय", "कितनी देर",
        "ab kitna chalna hai aur kitna door hai", "kitna chalna hai aur kitna door hai",
        "अब कितना चलना है और कितना दूर है", "कितना चलना है और कितना दूर है",
        "kitna chalna", "kitna chalna hai", "kitna chalna padega", "kitna chalna padega mujhe",
        "aur kitna chalna", "aur kitna chalna hai", "aur kitna chalna hai mujhe", "aur kitna chalna padega", "abhi aur kitna chalna hai",
        "kitani there chalana", "kitani der chalana", "kitni there chalana", "kitni der chalana",
        "kitni der chalna", "kitni der chalna hai", "kitni der aur chalna hai", "kitni der aur chalna padega",
        "kitna time chalna", "kitna time chalna padega", "chalna kitna baki hai", "kitna chalna bacha hai",
        "chalna kitna hai", "kitna paidal chalna", "kitna paidal chalna hai",
        "aur kitna time", "aur kitna time lagega", "kitna time lagega", "kitna time bacha", "aur kitna time bacha hai", "kitni der bachi hai",
        "pahunchne me kitna time", "pahunchne me kitni der", "pahunchne me kitna time lagega",
        "how long do i have to walk", "how much do i have to walk", "how much walking is left",
        "how much more to walk", "how long to walk", "how many minutes to walk",
        "कितना चलना", "कितना चलना पड़ेगा", "कितना चलना पड़ेगा मुझे", "कितना चलना है",
        "और कितना चलना", "और कितना चलना है", "और कितना चलना है मुझे", "और कितना चलना पड़ेगा", "अभी और कितना चलना है",
        "और कितना time लगेगा", "और कितना समय लगेगा", "कितना time लगेगा", "कितना समय लगेगा",
        "कितनी देर लगेगी", "और कितनी देर लगेगी", "कितनी देर चलना", "कितनी देर चलना है", "कितनी देर और चलना है", "कितनी देर और चलना पड़ेगा",
        "पहुँचने में कितना टाइम लगेगा", "पहुँचने में कितनी देर है", "पहुँचने में कितना समय लगेगा",
        "कितना समय चलना", "कितना समय चलना पड़ेगा", "कितना पैदल चलना", "कितना चलना बाकी है", "कितना समय बाकी है", "कितना time बचा है", "और कितना time बचा है", "कितनी देर बाकी है", "कितना बाकी है",
        "ಎಷ್ಟು ಸಮಯ", "ಎಷ್ಟು ಹೊತ್ತು", "ಎಷ್ಟು ನಿಮಿಷ", "ಎಷ್ಟು ಟೈಮ್", "ಎಷ್ಟು ಸಮಯ ಬೇಕು", "ಎಷ್ಟು ಹೊತ್ತು ಆಗುತ್ತೆ",
        "ಎಷ್ಟು ನಡೆಯಬೇಕು", "ಇನ್ನೂ ಎಷ್ಟು ನಡೆಯಬೇಕು", "ಇನ್ನು ಎಷ್ಟು ನಡೆಯಬೇಕು", "ಎಷ್ಟು ಹೊತ್ತು ನಡೆಯಬೇಕು", "ಇನ್ನೂ ಎಷ್ಟು ಸಮಯ ಬೇಕು",
        "ನಡೆಯಬೇಕು ಎಷ್ಟು", "ವಾಕ್ ಎಷ್ಟು ಮಾಡಬೇಕು",
        "eshtu samaya", "eshtu hottu", "eshtu nimisha", "eshtu time", "eshtu time aagatte", "eshtu hottu aagatte",
        "eshtu nadeyabeku", "innu eshtu nadeyabeku", "eshtu hottu nadeyabeku", "innu eshtu time aagatte",
        "eshtu nadibeku", "innu eshtu nadibeku", "eshtu walk madbeku",
    ]),
    ("distance_left", [
        "how far", "how many meters", "how many metres", "how many km", "how many kilometers",
        "distance left", "remaining distance", "how far do i have to walk", "how many kilometers to walk",
        "how far is my destination", "how far is it", "how much distance is left", "how many meters left", "how many km left",
        "kitni door", "kitna door", "kitne meter", "kitne km", "कितनी दूर", "कितना दूर",
        "aur kitni door", "aur kitna door", "aur kitni door hai", "aur kitna door hai", "kitna door aur hai",
        "kitni door chalna", "kitni door chalna hai", "kitne kilometer chalna", "kitne meter chalna",
        "distance kitna bacha hai",
        "और कितना दूर है", "और कितनी दूर है", "कितनी दूर और है", "कितना दूर और है",
        "कितनी दूर चलना", "कितनी दूर चलना है", "कितने किलोमीटर चलना", "कितने मीटर चलना", "कितना रास्ता बचा है", "कितनी दूरी बची है",
        "ಎಷ್ಟು ದೂರ", "ಇನ್ನು ಎಷ್ಟು ದೂರ", "ಎಷ್ಟು ಮೀಟರ್", "ಎಷ್ಟು ಕಿಮಿ", "ಎಷ್ಟು ಕಿಲೋಮೀಟರ್", "ಇನ್ನೂ ಎಷ್ಟು ದೂರ ಇದೆ", "ಇನ್ನೂ ಎಷ್ಟು ದೂರ",
        "ಎಷ್ಟು ದೂರ ನಡೆಯಬೇಕು", "ಎಷ್ಟು ಕಿಲೋಮೀಟರ್ ನಡೆಯಬೇಕು", "ಎಷ್ಟು ಮೀಟರ್ ನಡೆಯಬೇಕು", "ಇನ್ನೂ ಎಷ್ಟು ಕಿಮಿ ನಡೆಯಬೇಕು",
        "eshtu doora", "innu eshtu doora", "eshtu meter", "eshtu km", "eshtu doora ide", "innu eshtu doora ide",
        "eshtu doora nadeyabeku", "eshtu km nadeyabeku", "eshtu meter nadeyabeku",
    ]),
    ("next_turn", [
        "next turn", "where do i turn", "where should i turn", "where to turn", "which way",
        "where should i go next", "where do i go next", "where to go next", "where should i go",
        "where do i go now", "where do i go", "which turn should i take", "which turn to take",
        "which way should i go", "which way do i go", "which road to take", "which road do i take",
        "what next", "what now", "next instruction", "turn next", "left or right", "left or right turn",
        "what should i do next", "what do i do next", "what is my next turn", "what is the next turn",
        "where to turn next", "what's next", "where to next",
        "next left", "next right", "kahan mudna", "kahan modna", "kahan mudun",
        "kidhar mudna", "kidhar modna", "kidhar turn", "kahan turn", "ab mujhe kahan",
        "ab main kahan jaun", "ab main kahan jaon", "ab kahan jana hai", "ab kidhar jana hai",
        "ab kidhar jaun", "kahan jana hai", "kidhar jana hai", "agla mod kaun sa hai",
        "agla turn kaun sa hai", "aage kahan mudna hai",
        "left jana hai ya right", "left ya right", "dayan ya bayan", "baen ya daen", "daen ya baen",
        "agla mod", "ab kya karna", "kya karna hai", "mudna hai", "modna hai", "aage kya karna hai",
        "अब मैं कहाँ जाऊँ", "अब मैं कहां जाऊं", "अब मैं कहाँ जाऊ", "अब मैं कहां जाऊ",
        "अब किधर जाना है", "किधर जाना है", "कहाँ जाना है", "कहाँ जाऊँ", "कहाँ जाऊं", "किधर जाऊँ", "किधर जाऊं",
        "अगला मोड़ कौन सा है", "अगला मोड़ कहाँ है", "आगे कहाँ मुड़ना है", "मुझे कहाँ जाना है",
        "किधर मुड़ना है", "कहाँ मुड़ना है अब", "लेफ्ट जाना है या राइट", "लेफ्ट या राइट", "दायाँ या बायाँ", "बायाँ या दायाँ",
        "दाएँ मुड़ना है या बाएँ", "बाएँ मुड़ना है या दाएँ", "आगे किधर जाना है",
        "अगला मोड़", "कहाँ मुड़", "कहां मुड़", "किधर मुड़", "अगला टर्न कौन सा है", "आगे क्या करना है", "अब क्या करना है",
        "ಮುಂದೆ ಎಲ್ಲಿ ತಿರುಗಬೇಕು", "ಎಲ್ಲಿ ತಿರುಗಬೇಕು", "ಮುಂದಿನ ತಿರುವು", "ಮುಂದೆ ಏನು", "ಎಲ್ಲಿ ಹೋಗಬೇಕು", "ಯಾವ ಕಡೆ", "ಎಲ್ಲಿ ತಿರುಗಲಿ", "ಮುಂದೆ ಯಾವ ಕಡೆ",
        "ಎಡಕ್ಕಾ ಬಲಕ್ಕಾ", "ಲೆಫ್ಟ್ ಅಥವಾ ರೈಟ್", "ಲೆಫ್ಟಾ ರೈಟಾ",
        "munde elli tirugabeku", "elli tirugabeku", "munde enu", "yava kade", "elli hogabeku", "munde elli thirugbeku", "elli thirugbeku",
        "edakka balakka", "left athava right", "lefta righta",
    ]),
]
_RULES = [(intent, [_collapse(p.lower()) for p in phrases]) for intent, phrases in RULES]

# Fallback when no phrase matches: one anchor word from each group is enough.
COMBOS = [
    ("traffic_ahead", _s("traffic", "ಟ್ರಾಫಿಕ್"), _s("kaisa", "hai", "ahead", "update", "condition", "status", "kitna", "hegide", "hegidhe", "ideya", "idheya", "jaasti", "ಹೇಗಿದೆ", "ಇದೆಯಾ")),
    ("delay", _s("delay", "tada", "ತಡ", "ಡಿಲೇ"), _s("kitna", "kitni", "traffic", "how", "much", "eshtu", "is", "there", "ಎಷ್ಟು", "aagatte")),
    ("incident", _s("accident", "jam", "blocked", "closed", "ಅಪಘಾತ", "ಜಾಮ್"), _s("any", "is", "koi", "ahead", "aage", "band", "ಆಗಿದೆಯಾ", "ಇದೆಯಾ", "aagidiya", "aagidheya")),
    ("next_turn", _s("kahan", "kidhar", "kaha", "where", "which", "कहाँ", "कहां", "किधर", "कहा", "कौन"),
     _s("mudna", "modna", "mudun", "modun", "turn", "lena", "lun", "jaun", "jana", "chalna", "mod", "go", "next", "way", "road", "जाऊँ", "जाऊं", "जाना", "जाऊ", "जाओ", "मुड़ना", "मोड़", "लूँ", "लेना")),
    ("next_turn", _s("where", "which"), _s("turn", "go", "next", "left", "right", "way", "road")),
    ("next_turn", _s("elli", "yava", "munde", "ಎಲ್ಲಿ", "ಯಾವ", "ಮುಂದೆ"),
     _s("tirugabeku", "thirugbeku", "tiruga", "thiruga", "hogabeku", "hogbeku", "hoga", "kade", "ತಿರುಗಬೇಕು", "ತಿರುಗಿ", "ಹೋಗಬೇಕು", "ಕಡೆ", "ತಿರುವು")),
    ("next_turn", _s("left", "right", "dayan", "bayan", "daen", "baen", "लेफ्ट", "राइट", "दायाँ", "बायाँ", "दाएँ", "बाएँ", "ಎಡ", "ಬಲ"),
     _s("ya", "or", "athava", "jana", "mudna", "modna", "hogbeku", "tirugbeku", "या", "ಅಥವಾ", "जाना", "मुड़ना", "मोड़ना")),
    ("time_left", _s("kitna", "kitni", "kitne", "kitani", "aur", "abhi", "how", "कितना", "कितनी", "कितने", "और"),
     _s("time", "der", "there", "samay", "minute", "min", "chalna", "chalana", "paidal", "walk", "long", "eta", "arrive", "reach", "bache", "bacha", "बाकी", "समय", "देर", "चलना", "पैदल", "टाइम")),
    ("time_left", _s("eshtu", "innu", "ಎಷ್ಟು", "ಇನ್ನೂ", "ಇನ್ನು"),
     _s("samaya", "hottu", "nimisha", "time", "nadeyabeku", "nadibeku", "walk", "ಸಮಯ", "ಹೊತ್ತು", "ನಿಮಿಷ", "ಟೈಮ್", "ನಡೆಯಬೇಕು", "ನಡಿಬೇಕು")),
    ("distance_left", _s("kitna", "kitni", "kitne", "how", "कितना", "कितनी", "कितने"),
     _s("door", "dur", "meter", "km", "kilometer", "far", "distance", "दूर", "किलोमीटर", "मीटर", "दूरी")),
    ("distance_left", _s("eshtu", "ಎಷ್ಟು"),
     _s("doora", "dur", "meter", "km", "ದೂರ", "ಮೀಟರ್", "ಕಿಮಿ")),
    ("on_route", _s("sahi", "theek", "galat", "right", "correct", "wrong", "lost", "bhatak", "bhool", "yahi", "idhar", "yahin",
                    "सही", "ठीक", "गलत", "भटक", "भूल", "यही", "यहीं", "इधर"),
     _s("raste", "rasta", "route", "ja", "jana", "jaa", "disha", "direction", "side", "taraf", "turn", "mod", "way", "track", "path",
        "chal", "gaye", "gaya", "gayi", "rahe", "rahi", "raha", "hoon", "hu",
        "रास्ते", "रास्ता", "टर्न", "मोड़", "दिशा", "जा", "जाना", "चल", "गए", "गया", "गई", "रहे", "रही", "रहा", "हूँ", "हूं", "सड़क")),
    ("on_route", _s("sari", "sariyada", "tappu", "tappidhe", "tappiddheva", "ide",
                    "ಸರಿ", "ಸರಿಯಾದ", "ತಪ್ಪು", "ತಪ್ಪಿದೆ", "ತಪ್ಪಿದ್ದೇವಾ", "ಇದೇ"),
     _s("dari", "daari", "dharina", "darina", "dariya", "dhariya", "marga", "raste", "route", "hogtiddiva", "hogtiddeeva",
        "ದಾರಿ", "ದಾರಿನಾ", "ಮಾರ್ಗ", "ರಸ್ತೆ")),
    ("arrived_check", _s("did", "have", "are", "am", "kya", "क्या", "हम"),
     _s("arrive", "arrived", "reach", "reached", "there", "pahunch", "पहुँच", "पहुंच", "मंज़िल", "मंजिल")),
]


def _has(norm: str, phrase: str) -> bool:
    if not phrase.isascii():
        return phrase in norm
    if f" {phrase} " in f" {norm} ":
        return True
    if len(phrase) >= FUZZY_MIN_LEN and len(norm) >= len(phrase) - 3:
        return fuzz.partial_ratio(phrase, norm) >= FUZZY_SCORE
    return False


def detect_lang(text: str, norm: str) -> str:
    if _KANNADA.search(text):
        return "kn"
    has_dev = bool(_DEVANAGARI.search(text))
    words = set(norm.split())
    if words & _KANGLISH:
        return "kn"
    if has_dev:
        latin_words = [w for w in words if w.isascii() and len(w) > 1 and not w.isdigit()]
        if latin_words:
            return "hinglish"
        return "hi"
    if words & _HINGLISH:
        return "hinglish"
    return "en"


def classify(text: str) -> tuple[str, str]:
    norm = _norm(text)
    lang = detect_lang(text, norm)

    for intent, phrases in _RULES:
        for p in phrases:
            if _has(norm, p):
                return intent, lang

    words = set(norm.split())
    for intent, a, b in COMBOS:
        if (words & a) and (words & b):
            return intent, lang

    return "unknown", lang
