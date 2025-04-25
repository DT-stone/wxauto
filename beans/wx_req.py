# -*- coding:utf-8 -*-

from pydantic import BaseModel


class WxContact(BaseModel):
    who: str
