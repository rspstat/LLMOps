# providers

모델 provider 추상화. 모든 provider는 같은 인터페이스를 따라 서로 교체할 수 있어야 한다.

예정: Jev, 상용 API(OpenAI/Anthropic 등), Hugging Face Transformers, vLLM(OpenAI 호환 서버)

> Jev는 선택지가 정해진 판정에만 사용한다. 글쓰기·깊은 추론은 다른 provider의 몫이다.
