# the sender cannot reopen some drafts it can compose

the write contract accepts a plain-text body of up to 100,000 utf-8 bytes. its reader applies a 16,384-byte string limit to the entire encoded gmail message. an accepted body can therefore exceed the reader's limit well before hitting the separate two-mib response budget. this affects the pre-send check and recovery. [content contract](https://github.com/NielsdaWheelz/jarvis/blob/cfd82ec/src/jarvis/write_tools.py#L127) · [draft parser](https://github.com/NielsdaWheelz/jarvis/blob/cfd82ec/src/jarvis/write_connectors.py#L266) · [field limit](https://github.com/NielsdaWheelz/jarvis/blob/cfd82ec/src/jarvis/write_connectors.py#L341)

in an offline round trip at `cfd82ec`, the normal encoder took a valid 12,000-byte ascii body and produced a 22,211-character raw field with the fixture's headers. the normal draft parser rejected it with `provider field raw is oversized`.

close when every admitted message size can be encoded and inspected under the declared mail-specific limits. verify the maximum and first refused size at draft creation, update, pre-send check and recovery, allowing for mime and transport encoding. a size refusal should identify the limit before a provider write.
