from eva import EVA

eva = EVA()

while True:
    msg = input("Du: ")
    answer = eva.receive(msg)
    print("EVA:", answer)
