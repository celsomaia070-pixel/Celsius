import sounddevice as sd
print('Input devices:')
for i, d in enumerate(sd.query_devices()):
    if d['max_input_channels'] > 0:
        print(f'  {i}: {d["name"]} (in={d["max_input_channels"]})')