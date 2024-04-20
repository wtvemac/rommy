#!/usr/bin/python

import argparse
import re
import json
import time
import fnmatch
import tempfile
import os
import shutil
import sys

sys.path.append(".")

from lib.build_meta import *
from lib.romfs_explode import *
from lib.romfs_implode import *
from lib.rom_blocks import *
from lib.utv_tools import *
from lib.lzss import *

class PATH_TYPE(Enum):
    NULL_PATH_OBJCT = 0x00
    UNPACKED_FOLDER = 0x01
    PACKED_ROM_FILE = 0x02

def do_fart():
    import pygame
    import base64
    import io

    the_intro_base64 = [
        b'''
        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
        4LczNM8CfEGSHEjHcJlHt/jLIo2oWiQhjpq3bNcB9BzbeHfzyNq3VcROa6w/LOlJ7s2h5IAe/+Mo
        xP4qQ+6zHdhoAJ101bad5KA8OVlzWjtQxRUSILf2AYG+bxEVN7e4deUrfiIr5foHl/9St/0D3/yo
        j/1Qz+qls4CisNz1RnyIaRWaSurAAVC87BTzJwkMAto0oq82eiSt428yoYKIf/MFGNN/Vv//08xW
        0fmKGDDt6blDDllk5S4KCmAuJQ75UjblSHWo/+MoxNgk8+52/HrK0Ep7xKxutRL0kvkvkflmtpli
        PrSqTEFNRTMuMTAwqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqkxBTUUzLjEw
        MKqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqTEFNRTMu
        /+MoxMcVyf4xlDCGmDEwMKqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq
        qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq
        qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq/+MYxMQAAAP8AAAAAKqqqqqqqqqqqqqqqqqq
        qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq/+MYxMQAAANIAAAA
        AKqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq
        qqqq
        ''',
        b'''
        /+NIxAAAAAAAAAAAAFhpbmcAAAAPAAAAHQAAGDAAAwMDEhISJSUlJSsrKzExMTE4ODhBQUFBSkpK
        WlpaWmNjY21tbXZ2dnaDg4OSkpKSn5+frq6urri4uL6+vr7ExMTOzs7X19fX4ODg5+fn5+3t7fPz
        8/P29vb5+fn5/Pz8////AAAAPExBTUUzLjEwMAQoAAAAAAAAAAAVCCQDaCEAAcwAABgwaCyn/gAA
        AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
        AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
        AAAA/+MYxAAAAAP8AUAAACQCRQRhihXQaEsXDU+Qy4ze9NN1fm5cLlFE6Z//0mfOMm6NjtEn//5v
        l75ek03jbc///929fY1Md9nT/+NYxDsnQ8I5kY1YAIUkIPQoAiG4dBH////UOZuhRpVv8HRNMTxO
        B0STItMzd/////8UbnjQd4ey8+SFjc8m0wNhUI584TB5II3cIf/////7CebrwaLXEtccNzfNhsLj
        o6U4LzxmdRcXlZMlI0BCvKrmmyZzelRQlCqbLR2pJ8EwKBgUDIMmIoamkpbqAqrgYBTA0mWbroUG
        MBACNbNaPhHQNtLGOZA3MoxWMJQabgFQEaA0pKkFAmZ2kyb2OQbCKUafF0FgGRta6pghXDF2QvUr
        g0SgjoVoOHGQWaJk8SoOGEh4YFIZkgLtsYYDxg0MroYAyRHB2HES4jZjdNmxU2ZDDZsY9GFiiaBK
        JsQJGSRyzKYMAgUBAcwgDyzKC4UCliihufWI1hpisEvjEDmHQ+YTBIcBzIAkAAPMUhUz8MjAAOMP
        Ax/3aiTty1nK7VB0lk60Uy/6ScENM4mGy+fp9YDyLMlHAzIM/+NoxPlnS8K3GZ3iIAx+MTGItHhO
        v4wkKjEwCMOCYxEHAcDBGBCwBkkEfYKdCQyJgM4zt2HHt55yuX5xOLu/QRSN2zD4bMRhsWB5jUCm
        AgIqRritq6lAyYBwSim1JdLSiEAM6WSxR+3V3Wo6a1rCL15fFJXfXXD8vhyWWImzuB6KVz1e84j4
        rvYvDzSGCLXdB1ASCTCYfAQ7TXfmclW70gjtavI5bD0ichzWSppAwCJWqtKmhKIkQYIAKaTpniV8
        xE9gThAIiZFSqYaZwuCsCyRwmqBsbVJn0hy2LqD1M1RDB2itiDGyX1LlgvBaKirX/4wVFRVa/+iB
        VhZr/5k8UaVb/pBED8WcVFTV+6FBc0oWOZv90aVZrv4HDynU1VrmKtdmj+ZiouWuIqKeqiP/1tYt
        a/+P/n/3//i77dLWDpFTWayAbiAIwcmApBqOrYXIGjyUFjuVU8hzWKnaKqWUdMNIk+sA9bwoctcU
        HwIKUoFmDoqcXjrIqOiVlV0nPSXMkQqJgEpaOYCUwYCf4Y4CQwUSi/0Amf8tBT/qUoC3lZDGMBCv
        6GKj/+rf9DP/zCn//+MoxP4qlCre/dBAAFLKyDsGZAzzGN0lLKFNxECv/7fjD3hU74TqkBEkeJiP
        ZfwAPjgzRihHBuH7li4uLilYoSCsF59/BlECkuKQQYmxjChI0sXcezpQ6ZjqBHN+5YbI6DRi2g93
        7xrSvTb/xLbfa3fDzEVfPPcTZB/2jvxoivvoff6J6J//dRL30iXVzBBj/+MoxNYbEvra/HpELL8f
        pINx5yvvoOHaBhQPkyA6by5ro0c7moV5YRm2IOMNGFiASidRybTyUpD4IZAUCg5Vh2w9EhKKmZAQ
        FZwxGXwdHKSmTkREQVlkN6Km6EuiWRI83gF+5+eVTevQmFyWBO8/0al1bq7EbAMgENgoWHETlzOs
        yxTRMAyFjiCc5oLmRMug/+MoxOwtdErLHkJZwLRAJJljsGYiqZusAtQWa/MTiTAHEhq7iCdglA2F
        mAIiFTeISIhGVNAARXgdzAEI6ju5poiAb6CBCFxECIAAAgQHfLuWdFh0EgUvFwCwNy0crB+WKF97
        kGidcuBgoIoTozUjk+OTy8H/SNn4l/Yh86doj5vSdTXqN2a+/z0awkLlH+kd/+M4xLkyozbGfMjY
        8CxUTFTp4sWKnSUFdFYaQIyBmrAFEtP89NuABKrXi5Lqm/QlZ/KK+v+zzadIpaVryFmDaVWqGArm
        aDFJiAkg3TJpvL3WYL17Fri3YaDUPRlqgsgNjgzUEqUgfHGlDw5FShWg6BseCkFpACweiEAsIxIr
        s1Q18M17FHNfsqqv6rqtRf7NZJsXP/67X+qrUNDf8qsCx1wzSt7XTXrcqlrFqzNcM3Htf///////
        ////6/8N///eqqpIUFRaQwwowUhYh8eo2l5BOZAUhiYQ/+M4xLkppDrO/09AAbd2hgRnGHDE3EOA
        Bi9GHRiSJB4oghUFoBBRigHmOxYZCAhi8OkQRMUA8yy9CyAFAZMKCwAW6AEAmMzWZVC8jBQLMUGs
        z6LAMHAF2MeaHABe+PJEAREZwJL0+0JjBDSsT/vVJGHBig9XdHFbbsvO4iq6artoLtpASgoCP0bj
        qVgULLHkMGNImTZVKAUDBxNVJCAvQ4cijckpDLFiywyNNObCOhgQ6ccXZ41Aqj1LwYgOpaOGpLVg
        wuDhjOUwm8cumgB7H/ibjzzzuxFA/+NYxN1eK8J52ZzQAMMIDC35EnTxYYTDVY3OLtFtF+ix2Srn
        TxgGUoJGPN2ZwhDYhzHtiG7b9xCQQJhhDklL+goXHEOhEcBRsmEAI+9sAIiFy4FFRtNLcJc3Bk2l
        yDwGcyEYhQZnsXd+1SZSzc5X79e3D9acqQ4PLwUMVWagsZubBC2b6OOzWH1VG4NybmrXDZgRacK/
        VMmD0ksctncMOlGoIyhicZYnTVKiAFfEu5qABv+c+x3VKISL1xjjfQ1pWdc00ne02W7/9fYlDuxm
        UymU1bsAJ0DsUMC0TBrX36R2JKoY1eYi1a+ZD+OWAah/AvclJkjxBcXguAV8gguInjWdEJw+caQr
        QR8nY8dNxnCyKCJsZUnknUkuTJVRR1U1GLrb5mbIrRUk6qkuq7uo2RR//+/drqNkTVAwTSLhfLhN
        jhNZxTJnjE8TReRXQWqcNlOtbIvMjVKgm6FkVmZ9A0TU6aBgaLTU/+M4xL80VCrG/9iAAbUqjVpf
        Xo+ii3mJqiXUTPg2Q1WDEAN8qgAGtaw1U/TSwE15cozMUs4n6FzFVCsVvn8/tx1k6eYffuxxyExz
        W5gEf+7NQ4+6gk3Hef/JXD7sP7CqbWXIbjbgKWLegamsU9A/j/wuY3S77oovSRuEnj3fmXjGa1jK
        BqnY9xX+67k68SXca+zL3cQ6SH3f8fYd3fM9tc/tRBEOo4440igxqUqYv1uXjHTJHGlmZ/6f/KVW
        QQHQ5Di3TAxZCEKHFuHe1znkZGd8wAROepgq/+M4xLgtzBayHsGFMYEUACDvtfAAq/96gWElDKEV
        ZZf336lJBq8lq/P3IxS50kapcNbv0ky+1uZd3kqsOm0Rn4OK153pRBcXZw1t5cxhw8wsJgyIgKg9
        EA8PwUAeAoAYXxDgx9rQ4yolGVeKiotRqXWjLPF3VzW8EEGI9GU99PU3uPtOv0+K62uRha5RF1V/
        HfMTUaVx0kf+8zf/H//x3E9fdVHawDWlEIeSKoNGVA1RVAsYJ7EcPWQOiQbXAOmnA8I5hyubNnKP
        lGeqLkQGYIYoxY71cZU5/+M4xMsv9Da+31hAAShGAgxcUY1GFlKFgINpI6+Ry7WmWlAj2q1ACFgM
        uomqFSQONDTTcaJmDNKBwEwZPqXsgTAMqDjIxsWK0UGhDkWVRjvCmLaJojysMsE4cKCOdGIQuUNM
        AbqNOZhLiTh8pDHSzAcbORsw06cCEn+mTfbVMmSYE5XTafqEohDSXl3QpRkLPJhRLhcQ8NWhY/zr
        Zz/W1Qcq6TMY5UQrWxanYXF/Beq+OrkLPKqfu2I+BppQxwWK1gRKqZ+4qV0/OZjgUbVbSd/5ELUz
        o/zL/+NIxNZF88Ki+Zt4JJe/jarRkaBwMI+SwIUn8w3+ocV7CXMGBHy9ZYT7DDNbNNw388RstSHG
        T6Hs0eNFePILnDU8dVwbR7OCoho1hQ2M7rlzDQX2mx9ZCLFuoDB4FRXwQI0ISl9NkMNJjnxZpIID
        C9ySUwQkhEJy5AQaGdG3kT7TY0MMGXOYIaNJYkiyYeoDQU8QNFA4TOvAjk88YTNsMTmKUgEN9Iws
        NRFkIjEl6XnZs4smxm6Y5J8BBTZDi48DILMubEb+QZ0YYsSAQQUBGCCtRZC4TWYAROk9RsDTU9kw
        3Zcp+iQbH4yMgHIfYsqxeIOiKgGbRhLlmrE0N1hofmkqnLayu2DHkV88tD+N/e7OUkkdWIwVTxO5
        cdh5Zmjy/+NYxNFQG8Kp2ZvQBGprzmGCUDd2t0jaIxvLLoYis/IIh+Tg00GRukijjcg2lzlWEMNo
        gkMAEc4uQYAAW/Vwp2q+2qdxHHhuB53PtqMSigm69jCxf3GbbSHejE3S9l1q3LMLlPV314Hta4vV
        QSBGnxRQ9wl1t82kudDPCzVkNJhASBTHeUa2hyFtyhYXHj3pjDnmkYgmNcoAqeN8frhY7K5g7kg1
        L05WFdRpCJhBQGjGVKNhhtoSTtAnKFAaBiKUqfVAg3pcIvtBL4zoXUoym/AM6upnIASYjhUSRzW0
        TUUVNajSmJUtVCNgKwLMrEYay7KpF4QPHnYe4t/NVa8pd2tTOF9ymppRUsyLJ9GRwMo7POA+jzTz
        OZmG4FdWrS48zxrU0qq0tlhCcsVnX+b64/LystXa+mUWr7tWOZVtT1Nulpa1qZiTvW5VGqbHGo5U
        TiHIOcFs0DwA8UIiLmb/mT/NajNzssyf/+NIxOtI28KrGZrASGrzFSUw7emo1XlUuq0MtvWaXHVq
        mqTUpylMUir6UESiUOuvM36G1KsctZzUaz+CILmGnXmCujalSmWHqkqhYEhNd1eCMewWUDqSG2Xn
        TB/AYMCAqsZAgp5BgwwAaAFrT0gTJiYcGBhlhD/SBsSgkmEoB52wOciNEqsZgnaEAFXdHgBjbCFq
        GUSCQMwJA2l424NM5TKKPKQJI5DIOHtgZIgHV+/gVAmJApKApfABYFg5EzARFyqiZ4qLa+WaXLhQ
        sg8x4seBssWO6+sYbi5UKBQqbdkjA/gwCa+6qmKhaOjXzOBXkvq6yvvBIliNxSvVIsSiYYgkTUgS
        s7krHBrLoedtKCGGdJywKzJx/bjbqySi/si1/+NYxNpQi8LS+ZrSIJy1/3/n1N3/i79yuL55+7kY
        gZ2FpJ1Ti2mTOizxSEfjL8xDmT73rzYpHuCqWYic7S2JZSWO/7j09tnbE59AOg+84KBsnqy/V2NX
        pdEIfgxsrJk9EOKLSMilZML///n7y/DD8nx3adGTVaXYnbIbvoIAu4fhXqdrRonJB/qCtmcpdygy
        dr5j0aXHe/ntOOApXmTQ1VXk4rfO2Ixr8pc72EvpoeIQEg52itZZYFgUgE4LGXkpieMBlBRRApfP
        MpjihtBicQIYuo8SA4xzhNwj8nD6LrOrLo5JseSZbqKBSJtC67Gh4qH28wOGBipS6kGPFw+qvQUp
        f1ompomtdq3k6g6CK01pF52+ta/7ov+tS///UpkvrRMDOyLNKZDS4XZqmsyOJmKmVfQMjc5lTI3U
        eKjJh33mAAQqLk/S7u+1gSa3Gzvt6HqIkgEFGv38dOHCJuDYA+ltaHinck4Q/+M4xPIxBAbS/diI
        ADE8JacqteQX6YOUVAMBoTdjzQIw0njVXsD4WXDOV7qbRCKRSzV0MjY4BpE/5rDvJb7sIsFSfUKH
        l9hM+ublZ9u9KZL/8/peWetKkTVyccGedDuY+RPuB83RD57/+Y1iY8kLkjYPwfNAgByYfQCBcu9w
        IKE1ZZJG7EWZoTqF5YEjSKUlkSJ6vOGttC4GoqEZO03S/VzB0qqb7grJEc1YPc3PpOqMDlUTIQIy
        PoWOFIgW6kb0STupFTppx4npa2Zu+fWkzpcBZpnlmfn5/+MoxPkn+s7a/npGzLqZn0xQ48//j04X
        1IQQorRob4Kgnc39v4xEaPUd2G+kqQ0VTQ6PJWNtItAa4INRBEMMNAIsTi8NgqjqY3i5h3VtkxDD
        /qevBDAsgpBgEJd8RMOSgwDuQ43NLhOdlSKjTLphKHLcMcEDoK9BpzSlAOZVm0qAMcGechF1hwqM
        1pSiAhC+/+MoxNwk1Dq++EmGbQ2fi+y8bMiyidD2OApm096liSCy+jWIquiO5xOLNYkMPxxicWYY
        6nM5iKR+ENLd+fchrE4480vdkDXIEgmedJ6Y2/EoebKhgHCfwldWdtRbLt6yRgdpARQ2oULGPvf/
        //P+u7Zm4G83OJVp/DYGq1VVQo6qR0s////fZrPZrJVMpSlL/+M4xMs16/LDGsDFaNDGMYCMCoKg
        qd/BoRUDRYmGZAmmWAA///3gSVb1worDT0LJZLlTQ2oGoaul3ZyVwOj4AQidSQEMjiA2zEREgxsD
        hxkiAVnm6gihYHJjGhEcgaFApwtuXFZMnGupJhDZw6kAo9p6xRby90F1rKwIBnBZOCg4BAJqlyou
        /ryw7Dhd5oTktddFrrkkqqJVS9S/0MBMyWBRJSrVXjZqVJjMp9Vf9VK/xfy5tHUrHTh+TCpkUqGM
        b/Yxi96a///7pojo8xmVqcTiRRnoCalD/+M4xL4xQ9bDHtDFLVF87zJp9/pAAG7/OgAf/LeEiJdP
        prO7P7e0oS9tAZG9WxYkRJp8nJ4m+XocIVQao6mHsvapXESFczrKwaImzaEkNSITh8UipcU5ueDV
        NVKUvzsjsJwVxacpSlK0q0Tt8dT+HwwSk04alP2bZil2bCl3RmZmjFGlEyH8bPjcP///bv8JZJf/
        /P+nIZ/sZLCaqud+Ma9IKKnUKGHold4oACv9KgAGOW744l1ZZNsLMhUKYpJH9lsO2J+FRWidt0IG
        vOk0x8kExZZMJTFw/+M4xMQlu9KpHnpGsB7rcDH1cRnpoTIpbcWWFRDQmOCUzG8aVdVxg1avkreb
        cY1hDAIkURytzOqjGHW5WM6ldSm8xZjvUzMaj3Oz2UL70W5zVqV2KqOhK////e6o6FNchjI5hLNl
        L0TX//0ukwNjjOBk+T/Hf29XKh0iZ9bsAB962Ow01dBUyzeIxLWI9YL7ysMWn0zVlYmuaDVmno7M
        QCQwqBjc+gMUCNnEyKXdL7k4t/heISU/79+ShEnvCKmiZf/1zvHd73/Tzt5aZu/IFIKQgwg+Xgse
        /+MoxPgmE9aEfsJErRkNgoDgRB40GjA0JPEcIAXswvNmIQz47u7mqu5jWu7i75+5i5r/r/aNuou5
        VaWu1pSansplJQtqAqsnexLGlLlJnAAmu1HoKh/ieaeskCqfAZGZokSpyJLZmcqjpw4kl5mdme7E
        kv////6rXR5yRwKElEiQUWRCuUpStMZvlKWUpZjO/+MoxOImvA6JHnjQuaYz5Sy/mMb/Lyl/0fVD
        PKUsxW5nlNKUrIbMYxqlL/82pS1b/////5jOpSzFvMGG5f8VwpWAIR1prrhENBX0//+j/J620Bqt
        1Yp///9aTEFNRTMuMTAwqqqqqqqqqqqqqqqqqqqqqgk8/ggcJaNxcmXeIFny84v//u////+TTEFN
        RTMu/+MoxMoelAp+PmGEPTEwMKqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq
        UFBR0U0F8b0bFdLVTEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        VVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxNIGKBYowGAAAFVVVVVVVVVVVVVV
        VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV/+MYxNsFwBIg
        AFgAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        VVVVVVVV/+MYxNACyAIooAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        VVVVVVVVVVVVVVVVVVVVVVVVVVVV/+MYxMQAAAP8AAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        ''',
        b'''
        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
        k0635r+/1KFwhB4Tg1QWXr/6u5NrvKQ6UZzVr/5+n+o+7c409Jfvm7uqQo0QhOHIgMaHwmHXXx/V
        V3dRcVLGOnP8vLXUkMudZuOPHPVz8/9RazTfHH//3Mw0w0q1NaqKmr/NWqMuvdJTwPMLKsAACXN4
        VYRWNOtKmcxSzlHMpA/0bRVHRBnTQBGmyqnFjG3XGtXGvVBjIwQ1Jhk0M2scsbkNP9FswICddqvQ
        pBhVUoAgK/qq6rGZqAt1f9Wq/+MoxPMojB6m/MLQiaxm1Y6X9L4aqqrVKNz6THnqrMf//1VzWdVS
        4x7M2pRtjWNM9DGqXWhjUMZN/5SoZ9S5UeZH/QrTSzOjzf//UrGcoUyqCt2IP7fAbQ46wgrpGK87
        gRbWHETbD69ZTlE5AJkNamoRMoiI8dJCLFToltBJT0ZhBiACj1AwUvEQKkyyJYKi/+MoxNMlfBqC
        WtDEvBSZtlFMQU1FMy4xMDBVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVgCgKgrUJQVBXnQVV
        TEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        VVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxMALcHpaQHvSBFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV/+MYxM0EsEo94DJMAVVVVVVVVVVV
        VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV/+MYxNAC
        0A4koBgAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        VVVVVVVVVVVV/+MYxMQAAAP8AAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        '''
    ]

    the_fart_base64 = b'''
    /+NIxAAAAAAAAAAAAFhpbmcAAAAPAAAACQAACCgAMzMzMzMzMzMzMzNcXFxcXFxcXFxcXHBwcHBw
    cHBwcHBwhYWFhYWFhYWFhYWZmZmZmZmZmZmZma6urq6urq6urq6uwsLCwsLCwsLCwsL19fX19fX1
    9fX19f//////////////AAAAPExBTUUzLjEwMAQoAAAAAAAAAAAVCCQEACEAAcwAAAgoeX+b7QAA
    AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
    AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
    AAAA/+NYxAAckXZ4H0wYAAArwAADgfEc/YJANAaEw/OxLBMAcAMCYjn9V69f7BIJkSyJszM38pqx
    zpxhYs6nbf8p2gAAn//u7v7oIRE93RERC64AAIclwQDGDgIAhUD4Pg+8Ew+IDkH+UDEHz4Pv//wQ
    cGPwx8oCAY/yjsTg/lAQBBVoCAAAAtVxpWz5vmoFFAqLghwVxmfj4NbhgGDQSBQPmX/OoaNmWA1E
    yIg2KgeRjIMwRBx0+L0vMQBSvWsJFRCALttu8hkhqyxnyEfJOMkPQexiwakJFnfJpEDeDQbXNUau
    pydggTVBGQKhhKAXU7XI5yVHecrcdJeR1yx3AXN86XZzqM8sro0SnQa0O8JCtQ2FtcRtGuYxtEtV
    LA8UBY10hD8050e2OBcVAc5BieN5ypozFabxyqWrYzq451Yyrg8k20MjIhg68f40qK78BmKMWhYh
    4+EWOfUeUnylUdEYaFc3RarVKPVr/+NIxOhFE8LCWZp4AJLAHxwxEv397qv///gwSEl0EYT66YGw
    u5aq7//v474/FSy6PhthMKhr//9R1YBeJLnAA+Ja5rBhtw+1IAKiwEUYxiljHwWM5lELGqZto2DL
    ZTSo9xY3zbLAu1QqSz7ziDu8+IDypTHTVpAleWL3yhRhVZF597SRykVwv9ccbctMmL9XPFvE3H3X
    aV8VKfKb+/f+iLfcV78VwvIz6pr/hheHl/ur0/+CTHWTf5P4m///////i//9RUHjr/UqgBiQN8AD
    +fudw7UeF2ppVZJaHnQGErDKzM5bSfqllHBPDULE9VTMhTMkXBkVlomdQcSbjt183ztyrdsXm1nj
    MYyzEfR51MNYQ444EGCCuxSsBBh94KCl/+MoxOYji+rc/89AAFqaaSiOzK1ClIx3RbuZCOVFqVjq
    hTVdn2DZjH/+xA9Q7FP/MZP/oqiRLH/5n/9/lt6uTU7oFd7dhyEJBOzqwABKkaSl4AD1roTtpttl
    x03EAMCRfA6JJKOg/HDa/9aHjoi3b3jFjyWZpxC6EqTbkydnpo8kQBToGbsIUyFuaFn/vmCG/+Mo
    xNolFB7ZFsPEVSFi4xq1LnONmsbQDP6WYfZtvi/yCCOHmA8cifQAHewoAhQMJHnoWa4h7xIHfJ2/
    ermGiFwPV2FWbYdqlAJBUbCd4AG/0P3JC7zz2VDMEXnQVKhmEk7IA4MkEhmUy2r43JXJRK4ol6mW
    LLUV+XveefIMex1PcPTq1qxARqAkZPUFCnak/+MoxMgf0hbmXmGGrGwUjk6UL/qrP846//AKlo6Z
    TcMI1vP1nWRjBFKEwVFi4u9S7Cof8OT3/kZKKf+TsQAJcc14AB3e7GSbOt2mnnkvV5GXUjlCfVng
    S3hMz6LmNJBtAngzVntDe49pNvsaiiSFbgwEEHan+zg2FtXHFFWNLQsdlD1zdDPlVXT6hqJbrZHH
    /+MoxMsdwmbiXkmGdKSXWS3UyrE9kFJeZFEh8696X5Ehrd+h/Yz0yERuMWoIgXi6LfPPoiFuWFXe
    W16alDoOAodCgFBgbDUkKVjtnMaFEEkAxAszHBv//9ojO2XKwjR4HBaYcC5j8rf/+mNPPCj6ZYl5
    iRAmqieanqX//yF/m2Z03FzTPZA4kKOI6TKmkoqD/+MoxNcgovLOV08YAGGY////UFkLUmTPw2Fw
    XdMtcjbwg3TNNIjTSiA0kuBoQDQX/////24UWlDk3aR4oHkJixKFgkeEDI0QxEqMFBwQDGAiCD6p
    P//////q0T4y7N4KLOC4eqTSA0yEsMObzBD02I5NNwjN4w48kN86TSpsI6Dc57///////+K0dWXQ
    7BVS/+NYxNdOe3qqWZzYYNx+LTlqUzRkKUZOFmbHZgw+YADGMiBgpMLJRmTGY8imNBhj4InMn7//
    ///////xaNR2Do5K7s/RYzFPlbvZR6nTBXimqCRAGhwcPGFE4EER4IMHDgqDFYCYIJhYDUgWeQnJ
    BUxBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1F
    My4xMDBVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
    VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
    VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
    VVVVVVVVVVVVVVVVVVVVVVVVVVVV/+MYxMQAAANIAcAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
    VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
    '''
    the_fart = base64.b64decode(the_fart_base64)

    tuned_fart = [
        250,
        random.randrange(10, 500),
        random.randrange(10, 150),
        random.randrange(10, 150),
        random.randrange(10, 150),
        random.randrange(10, 150),
        random.randrange(10, 500)
    ]

    pygame.mixer.init()

    pygame.mixer.music.load(io.BytesIO(base64.b64decode(random.choice(the_intro_base64))))
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

    pygame.mixer.music.load(io.BytesIO(the_fart)) 
    for delay in tuned_fart:
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

        time.sleep(delay / 1000)
        pygame.mixer.music.rewind()
    
    pygame.mixer.music.stop()

def find_file(pattern, search_dir):
    objects = listdir(search_dir)

    for name in objects:
        if fnmatch.fnmatch(name, pattern):
            return name

    return None

def info(in_path, no_matryoshka = False, no_autodisk = False, no_data_section = False, no_romfs = False, no_nk = False, no_nk_registry = False, is_rom_blocks = False):
    in_type = PATH_TYPE.NULL_PATH_OBJCT
    if os.path.isdir(in_path):
        in_type = PATH_TYPE.UNPACKED_FOLDER
    elif os.path.isfile(in_path):
        in_type = PATH_TYPE.PACKED_ROM_FILE
    else:
        raise Exception("Invalid input path. Please check that the path exists")


    if os.path.isdir(in_path):
        if is_rom_blocks and rom_blocks.count_rom_parts(in_path) > 0:
            print("\n=== ROM Upgrade Blocks ===\n")
            rom_blocks.list(in_path, True)
        else:
            print("Can't get info for this folder")
    elif in_type == PATH_TYPE.PACKED_ROM_FILE:
        build_info = build_meta.detect(in_path)

        build_meta.print_build_info(build_info)

        if "image_type" in build_info and build_info["image_type"] == IMAGE_TYPE.ULTIMATETV_BOX:
            utv_tools.list(in_path, no_nk, no_romfs, True)
        else:
            if not no_romfs:
                print("\n=== ROMFS Files ===\n")
                romfs_explode.list(in_path, True, "" if no_matryoshka else None)

            if not no_autodisk:
                print("\n\n=== Autodisk Files ===\n")
                autodisk.list(in_path, True)

def fixcs(in_path):
    print("Checking checksum for '" + in_path + "'")

    build_blob = bytearray(open(in_path, "rb").read())

    updated_blob = False

    code_size = int.from_bytes(bytes(build_blob[0x10:0x14]), "big") << 2
    if len(build_blob) >= code_size:
        current_checksum = int.from_bytes(bytes(build_blob[0x08:0x0c]))

        build_blob[0x08:0x0c] = bytearray(0x04)
        calculated_checksum = build_meta.chunked_checksum(build_blob[0x00:code_size])

        print("\tCalculated code checksum: " + hex(calculated_checksum) + ", Current code checksum: " + hex(current_checksum))

        if calculated_checksum != current_checksum:
            print("\t\tFixing code checksum")

            build_blob[0x08:0x0c] = bytearray(0x04)
            struct.pack_into(
                ">I",
                build_blob,
                0x08,
                calculated_checksum
            )

            updated_blob = True

        else:
            print("\t\tCode checksum matches, no need to fix!")

    else:
        print("Unable to checksum. File length seems bogus?")

    if updated_blob:
        open(in_path, "wb").write(build_blob)

def process_file_to_folder(in_path, template_path, level1_path, out_path, silent = False, no_matryoshka = False, no_autodisk = False, no_data_section = False, no_romfs = False, no_nk = False, no_nk_registry = False, no_template = False):
    in_build_info = build_meta.detect(in_path)

    if in_build_info != None and "image_type" in in_build_info and IMAGE_TYPE(in_build_info["image_type"]) == IMAGE_TYPE.ULTIMATETV_BOX:
        utv_tools.unpack(in_path, out_path, silent, True, no_romfs, no_nk, no_nk_registry)
    else:
        romfs_explode.unpack(in_path, out_path, silent, level1_path, True, no_romfs)

        if os.path.isfile(out_path + "/dt.json"):
            dt = json.load(open(out_path + "/dt.json", "r"))

            box_builds = [
                IMAGE_TYPE.BOX,
                IMAGE_TYPE.COMPRESSED_BOX,
                IMAGE_TYPE.COMPRESSED_BOOTROM,
                IMAGE_TYPE.ORIG_CLASSIC_BOX
            ]

            template_path = None
            template_file = None
            if "template_file" in dt and dt["template_file"] != None:
                if os.path.isfile(out_path + "/" + dt["template_file"]):
                    template_file = dt["template_file"]
                    template_path = out_path + "/" + dt["template_file"]
                elif os.path.isfile(dt["template_file"]):
                    template_file = dt["template_file"]
                    template_path = dt["template_file"]
            elif os.path.isfile(in_path + "/template.bin"):
                template_file = "template.bin"
                template_path = in_path + "/template.bin"
            dt["template_file"] = template_file
            level0_build_info = None
            if template_path != None:
                level0_build_info = build_meta.detect(template_path)

            dt["level0_data_file"] = ""
            if template_path != None and level0_build_info != None:
                if "image_type" in level0_build_info and IMAGE_TYPE(level0_build_info["image_type"]) in box_builds:
                    if not no_autodisk and "autodisk_offset" in level0_build_info and level0_build_info["autodisk_offset"] > 0:
                        if not silent:
                            print("\nExtracting level0 autodisk files")
                        dt["level0_autodisk_objects"] = autodisk.unpack(template_path, out_path + "/level0-autodisk", silent)

                    if not no_data_section and "build_address" in level0_build_info and "data_address" in level0_build_info != None and "data_size" in level0_build_info:
                        if level0_build_info["build_address"] > 0 and level0_build_info["data_address"] > 0 and level0_build_info["data_size"] > 0:
                            data_offset = level0_build_info["data_address"] - level0_build_info["build_address"]

                            if data_offset > 0 and IMAGE_TYPE(level0_build_info["image_type"]) != IMAGE_TYPE.COMPRESSED_BOX:
                                if not silent:
                                    print("\nExtracting level0 .data")

                                with open(template_path, "rb") as f:
                                    f.seek(0, os.SEEK_END)
                                    file_size = f.tell()

                                    data_size = level0_build_info["data_size"]
                                    if "compressed_data_size" in level0_build_info and level0_build_info["compressed_data_size"] > 0:
                                        data_size = level0_build_info["compressed_data_size"]

                                    f.seek(data_offset)
                                    data = f.read(data_size)

                                    if level0_build_info["build_flags"] != None and ((level0_build_info["build_flags"] & 0x01) == 0x01) and "compressed_data_size" in level0_build_info:
                                        d = lzss()
                                        data = d.Lzss_Expand(data, level0_build_info["data_size"])

                                    level0_build_info["build_flags"]

                                    dt["level0_data_file"] = "level0_data_" + hex(level0_build_info["data_address"]) + "-" + hex(level0_build_info["data_address"] + len(data))  + ".bin"
                                    open(out_path + "/" + dt["level0_data_file"], "wb").write(data)

                                    if not silent:
                                        print("Done.")

                dt["level0_build_info"] = level0_build_info

            level1_path = None
            level1_file = None
            if "level1_file" in dt and dt["level1_file"] != None:
                if os.path.isfile(out_path + "/" + dt["level1_file"]):
                    level1_file = dt["level1_file"]
                    level1_path = out_path + "/" + dt["level1_file"]
                elif os.path.isfile(dt["level1_file"]):
                    level1_file = dt["level1_file"]
                    level1_path = dt["level1_file"]
            elif os.path.isfile(in_path + "/level1.bin"):
                level1_file = "level1.bin"
                level1_path = in_path + "/level1.bin"
            dt["level1_file"] = level1_file
            level1_build_info = None
            if level1_path != None:
                level1_build_info = build_meta.detect(level1_path)

            dt["level1_data_file"] = ""
            if level1_path != None and level1_build_info != None:
                if "image_type" in level1_build_info and IMAGE_TYPE(level1_build_info["image_type"]) in box_builds:
                    if not no_autodisk and "autodisk_offset" in level1_build_info and level1_build_info["autodisk_offset"] > 0:
                        if not silent:
                            print("\nExtracting level1 autodisk files")
                        dt["level1_autodisk_objects"] = autodisk.unpack(level1_path, out_path + "/level1-autodisk", silent)

                    if not no_data_section and "build_address" in level1_build_info and "data_address" in level1_build_info and "data_size" in level1_build_info:
                        if level1_build_info["build_address"] > 0 and level1_build_info["data_address"] > 0 and level1_build_info["data_size"] > 0:
                            data_offset = level1_build_info["data_address"] - level1_build_info["build_address"]

                            if data_offset > 0:
                                if not silent:
                                    print("\nExtracting level1 .data")

                                with open(level1_path, "rb") as f:
                                    f.seek(0, os.SEEK_END)
                                    file_size = f.tell()

                                    data_size = level1_build_info["data_size"]
                                    if "compressed_data_size" in level1_build_info and level1_build_info["compressed_data_size"] > 0:
                                        data_size = level1_build_info["compressed_data_size"]

                                    f.seek(data_offset)
                                    data = f.read(data_size)

                                    if level1_build_info["build_flags"] != None and ((level1_build_info["build_flags"] & 0x01) == 0x01) and "compressed_data_size" in level1_build_info:
                                        d = lzss()
                                        data = d.Lzss_Expand(data, level1_build_info["data_size"])

                                    dt["level1_data_file"] = "level1_data_" + hex(level1_build_info["data_address"]) + "-" + hex(level1_build_info["data_address"] + len(data))  + ".bin"
                                    open(out_path + "/" + dt["level1_data_file"], "wb").write(data)

                                    if not silent:
                                        print("Done.")

                dt["level1_build_info"] = level1_build_info

            with open(out_path + "/dt.json", "w") as f:
                f.write(json.dumps(dt, sort_keys=True, indent=4))
                f.close()

def process_folder_to_file(in_path, template_path, level1_path, out_path, out_file_type, silent = False, no_matryoshka = False, no_autodisk = False, no_data_section = False, no_romfs = False, no_nk = False, no_nk_registry = False, no_template = False, level0_data_path = None, level1_data_path = None, level1_lzj_version = None, autodisk_path = None):
    box_types = [
        IMAGE_TYPE.BOX,
        IMAGE_TYPE.COMPRESSED_BOX,
        IMAGE_TYPE.COMPRESSED_BOOTROM,
        IMAGE_TYPE.ORIG_CLASSIC_BOX,
    ]

    level0_romfs_folders = []
    level1_romfs_folders = []
    unknown_romfs_folders = []
    if os.path.isdir(in_path + "/level0-romfs"):
        level0_romfs_folders.append(in_path + "/level0-romfs")

    if os.path.isdir(in_path + "/level0-compressfs"):
        level0_romfs_folders.append(in_path + "/level0-compressfs")

    if os.path.isdir(in_path + "/level1-romfs"):
        level1_romfs_folders.append(in_path + "/level1-romfs")

    if os.path.isdir(in_path + "/ROM"):
        unknown_romfs_folders.append(in_path + "/")


    if len(level0_romfs_folders) == 0 and len(level1_romfs_folders) == 0 and len(unknown_romfs_folders) == 0:
        no_romfs = True

    level0_build_info = None
    level1_build_info = None
    dt = {}

    if os.path.isfile(in_path + "/dt.json"):
        dt = json.load(open(in_path + "/dt.json", "r"))

        if template_path == None:
            if "template_file" in dt and dt["template_file"] != None:
                if os.path.isfile(in_path + "/" + dt["template_file"]):
                    template_path = in_path + "/" + dt["template_file"]
                elif os.path.isfile(dt["template_file"]):
                    template_path = dt["template_file"]


    if template_path == None:
        if os.path.isfile(in_path + "/template.bin"):
            template_path = in_path + "/template.bin"
        elif os.path.isfile(out_path):
            template_path = out_path

    if template_path == None and out_file_type != IMAGE_TYPE.COMPRESSED_BOX:
        specify_info = "This can be specified within the dt.json file at the root of the IN folder, a template.bin file at the root of the IN folder, using the --template-image-file command line option or if the output file already exists that we can build into."
        if out_file_type in box_types:
            raise Exception("Can't create ROM image without a template file. " + specify_info)
        else:
            print("Since we have no template file that exist we will create a ROMFS file. If you expected a ROM image file then please specify a template file. " + specify_info)

    if template_path != None and os.path.isfile(template_path):
        level0_build_info = build_meta.detect(template_path)
    
    if not no_matryoshka:
        if level1_path != None and not os.path.isfile(level1_path):
            level1_path = None

        if level1_path == None:
            if "level1_file" in dt and dt["level1_file"] != None:
                if os.path.isfile(in_path + "/" + dt["level1_file"]):
                    level1_path = in_path + "/" + dt["level1_file"]
                elif os.path.isfile(dt["level1_file"]):
                    level1_path = dt["level1_file"]
            elif os.path.isfile(in_path + "/level1.bin"):
                level1_path = in_path + "/level1.bin"

        if level1_path != None:
            level1_build_info = build_meta.detect(level1_path)

    if out_file_type == None and level0_build_info != None and "image_type" in level0_build_info:
        out_file_type = level0_build_info["image_type"]

    if re.search(r"\.(vwr)$", out_path, re.IGNORECASE) != None:
        out_file_type = IMAGE_TYPE.VIEWER_SCRAMBLED
    elif re.search(r"WEBTV\.ROM$", out_path, re.IGNORECASE) != None:
        out_file_type = IMAGE_TYPE.DREAMCAST
        
    if out_file_type == None:
        if re.search(r"\.(o|rom)$", out_path, re.IGNORECASE) != None:
            out_file_type = IMAGE_TYPE.BOX
        elif re.search(r"\.(brom)$", out_path, re.IGNORECASE) != None:
            out_file_type = IMAGE_TYPE.COMPRESSED_BOOTROM
        else:
            out_file_type = IMAGE_TYPE.VIEWER

    if out_file_type == IMAGE_TYPE.VIEWER_SCRAMBLED and no_matryoshka:
        raise Exception("Can't generate a scrambled viewer ROMFS file when --no-matryoshka is specified.")
    elif out_file_type == IMAGE_TYPE.COMPRESSED_BOX and no_matryoshka:
        raise Exception("Can't generate a compressed box ROM file when --no-matryoshka is specified.")
    #elif out_file_type == IMAGE_TYPE.ORIG_CLASSIC_BOX or out_file_type == IMAGE_TYPE.ORIG_CLASSIC_BOOTROM:
    #    raise Exception("Can't build any original classic images")

    if out_file_type == IMAGE_TYPE.ULTIMATETV_BOX:
        utv_tools.pack(in_path, out_path, template_path, silent, level0_build_info, True, no_romfs, no_nk, no_nk_registry)
    elif not out_file_type in box_types:
        romfs_implode.pack(in_path, level0_romfs_folders + level1_romfs_folders + unknown_romfs_folders, template_path, out_path, out_file_type, "", None, b'', b'', silent, level0_build_info, "level0", True, no_romfs, False)
    else:
        if template_path != None:
            level0_build_info = build_meta.detect(template_path)

        if level0_build_info == None or not "image_type" in level0_build_info:
            raise Exception("Can't generate box build without a box build template.")
        elif out_file_type != level0_build_info["image_type"]:
            if out_file_type == IMAGE_TYPE.COMPRESSED_BOX:
                print("NOTE: Building from template file '" + template_path + "' to compressed box image.")
            else:
                raise Exception("Can't generate box build without a box build template of the same target type. Sorry, not good enough (yet?) to generate a box build out of thin air. (out_type=" + str(out_file_type) + ", template_type=" + (str(level0_build_info["image_type"]) if level0_build_info != None and "image_type" in level0_build_info else str(None)) + ")")

        built_level1_path = ""
        if not no_matryoshka and (out_file_type == IMAGE_TYPE.COMPRESSED_BOX or out_file_type == IMAGE_TYPE.COMPRESSED_BOOTROM):
            if level1_build_info == None:
                if out_file_type == IMAGE_TYPE.COMPRESSED_BOX:
                    level1_build_info = level0_build_info
                    if template_path != None and os.path.isfile(template_path):
                        level1_path = template_path
                        level1_build_info = level0_build_info
                    else:
                        raise Exception("Need a level1 file to create a compressed box image. At the very least make sure a template.bin file is in the input folder.")
                else:
                    raise Exception("I'm unable to get the level1 image template info. This target type has a image inside an image and I need both templates to continue. Use --no-matryoshka to skip this and go straight to the root level. (level1_path=" + str(level1_path) + ")")

            level1_data = b''
            if not no_data_section:
                if level1_data_path != None and not os.path.isfile(level1_data_path):
                    level1_data_path = None
                if level1_data_path == None:
                    if "level1_data_file" in dt and dt["level1_data_file"] != None:
                        if os.path.isfile(in_path + "/" + dt["level1_data_file"]):
                            level1_data_path = in_path + "/" + dt["level1_data_file"]
                        elif os.path.isfile(dt["level1_data_file"]):
                            level1_data_path = dt["level1_data_file"]
                if level1_data_path == None:
                    level1_data_path = find_file("level1_data_*.bin", in_path)

                if level1_data_path != None and os.path.isfile(level1_data_path):
                    level1_data = bytearray(open(level1_data_path, "rb").read())

            if out_file_type == IMAGE_TYPE.COMPRESSED_BOX and (level1_data == None or len(level1_data) <= 0):
                if "level0_data_file" in dt and dt["level1_data_file"] != None:
                    if os.path.isfile(in_path + "/" + dt["level0_data_file"]):
                        level0_data_path = in_path + "/" + dt["level0_data_file"]
                    elif os.path.isfile(dt["level0_data_file"]):
                        level0_data_path = dt["level0_data_file"]

                if level0_data_path == None:
                    level0_data_path = find_file("level0_data_*.bin", in_path)

                if level0_data_path != None and os.path.isfile(level0_data_path):
                    level1_data = bytearray(open(level0_data_path, "rb").read())

            if not silent:
                print("Creating level1 image.")

            built_level1_path = tempfile.mktemp()

            _romfs_folders = []
            if not no_romfs:
                if len(level1_romfs_folders) > 0:
                    _romfs_folders = level1_romfs_folders
                elif out_file_type == IMAGE_TYPE.COMPRESSED_BOX:
                    if len(unknown_romfs_folders) > 0:
                        _romfs_folders = [unknown_romfs_folders.pop()]

                    if len(_romfs_folders) == 0 and len(level0_romfs_folders) > 0:
                        _romfs_folders = level0_romfs_folders

            cb_level0_audodisk_data =  b''
            if out_file_type == IMAGE_TYPE.COMPRESSED_BOX and not no_autodisk:
                if autodisk_path != None and not os.path.isdir(autodisk_path):
                    autodisk_path = None

                if autodisk_path == None:
                    if os.path.isdir(in_path + "/level1-autodisk"):
                        autodisk_path = in_path + "/level1-autodisk"
                    elif os.path.isdir(in_path + "/level0-autodisk"):
                        autodisk_path = in_path + "/level0-autodisk"

                if autodisk_path != None and os.path.isdir(autodisk_path):
                    audodisk_data = autodisk.build_image([autodisk_path], level0_build_info, silent, dt)

            # LZJ is better than any ROMFS compression so leave it uncompressed and let LZJ do its thing
            disable_romfs_compression = (out_file_type == IMAGE_TYPE.COMPRESSED_BOOTROM and "bootrom_level1_compression" in level0_build_info and level0_build_info["bootrom_level1_compression"] == FILE_COMPRESSION.LZJV1)

            romfs_implode.pack(in_path, _romfs_folders, level1_path, built_level1_path, level1_build_info["image_type"], "", None, level1_data, cb_level0_audodisk_data, silent, level1_build_info, "level1", True, no_romfs, disable_romfs_compression)

        level0_data = b''
        if not no_data_section:
            if level0_data_path != None and not os.path.isfile(level0_data_path):
                level0_data_path = None
            if level0_data_path == None:
                if "level0_data_file" in dt and dt["level1_data_file"] != None:
                    if os.path.isfile(in_path + "/" + dt["level0_data_file"]):
                        level0_data_path = in_path + "/" + dt["level0_data_file"]
                    elif os.path.isfile(dt["level0_data_file"]):
                        level0_data_path = dt["level0_data_file"]
            if level0_data_path == None:
                level0_data_path = find_file("level0_data_*.bin", in_path)

            if level0_data_path != None and os.path.isfile(level0_data_path):
                level0_data = bytearray(open(level0_data_path, "rb").read())

        audodisk_data = b''
        if not no_autodisk:
            if autodisk_path != None and not os.path.isdir(autodisk_path):
                autodisk_path = None
            if autodisk_path == None:
                if os.path.isdir(in_path + "/level0-autodisk"):
                    autodisk_path = in_path + "/level0-autodisk"

            if autodisk_path != None and os.path.isdir(autodisk_path):
                audodisk_data = autodisk.build_image([autodisk_path], level0_build_info, silent, dt)

        if not silent:
            print("Creating level0 image.")

        _romfs_folders = []
        if not no_romfs:
            if len(level0_romfs_folders) > 0:
                _romfs_folders = level0_romfs_folders
            elif len(unknown_romfs_folders) > 0:
                _romfs_folders = [unknown_romfs_folders.pop()]
                
        romfs_implode.pack(in_path, _romfs_folders, template_path, out_path, out_file_type, built_level1_path, level1_lzj_version, level0_data, audodisk_data, silent, level0_build_info, "level0", True, no_romfs, False)

        if built_level1_path != None and os.path.isfile(built_level1_path) and template_path != built_level1_path:
            os.remove(built_level1_path)

def process_file_to_file(in_path, template_path, level1_path, out_path, out_file_type, silent = False, no_matryoshka = False, no_autodisk = False, no_data_section = False, no_romfs = False, no_nk = False, no_nk_registry = False, no_template = False, level0_data_path = None, level1_data_path = None, level1_lzj_version = None, autodisk_path = None):
    in_build_info = build_meta.detect(in_path)

    if in_build_info != None and "image_type" in in_build_info and IMAGE_TYPE(in_build_info["image_type"]) != IMAGE_TYPE.COMPRESSED_BOX and out_file_type == IMAGE_TYPE.COMPRESSED_BOX:
        level0_build_info = build_meta.default_build_info(out_path)

        if template_path == None:
            template_path = in_path

        level0_build_info["image_type"] = IMAGE_TYPE.COMPRESSED_BOX

        romfs_implode.pack(in_path, [], template_path, out_path, IMAGE_TYPE.COMPRESSED_BOX, in_path, level1_lzj_version, b'', b'', silent, level0_build_info, "level0", True, no_romfs, False)
    else:
        tmp_dump_path = tempfile.mktemp()

        process_file_to_folder(in_path, template_path, level1_path, tmp_dump_path, silent, no_matryoshka, no_autodisk, no_data_section, no_romfs, no_nk, no_nk_registry, no_template)

        process_folder_to_file(tmp_dump_path, template_path, level1_path, out_path, out_file_type, silent, no_matryoshka, no_autodisk, no_data_section, no_romfs, no_nk, no_nk_registry, no_template, level0_data_path, level1_data_path, level1_lzj_version, autodisk_path)

        if tmp_dump_path != None and os.path.isdir(tmp_dump_path):
            shutil.rmtree(tmp_dump_path)

def process(in_path, template_file, out_path, out_file_type = None, silent = False, no_matryoshka = False, no_autodisk = False, no_data_section = False, no_romfs = False, no_nk = False, no_nk_registry = False, no_template = False, level1_path = None, level0_data_path = None, level1_data_path = None, level1_lzj_version = None, autodisk_path = None, is_rom_blocks = False, is_build_folder = True, rom_block_size = None, rom_block_address_base = None, rom_block_header_version = None, rom_block_compression_type = None, rom_block_signature_type = None, rom_block_message = ""):
    in_type = PATH_TYPE.NULL_PATH_OBJCT
    if os.path.isdir(in_path):
        in_type = PATH_TYPE.UNPACKED_FOLDER
    elif os.path.isfile(in_path):
        in_type = PATH_TYPE.PACKED_ROM_FILE
    else:
        raise Exception("Invalid input path. Please check that the path exists")

    out_type = PATH_TYPE.NULL_PATH_OBJCT
    out_exists = False
    if out_path != None:
        if os.path.isdir(out_path):
            out_exists = True
            out_type = PATH_TYPE.UNPACKED_FOLDER
        elif os.path.isfile(out_path):
            out_exists = True
            out_type = PATH_TYPE.PACKED_ROM_FILE
        else:
            out_exists = False
            out_type = PATH_TYPE.UNPACKED_FOLDER

    template_path = None
    if not no_template:
        if template_file != None:
            if os.path.isfile(template_file):
                template_path = template_file
            else:
                raise Exception("The template file must exist!")

    if os.path.isfile(in_path):
        in_type = PATH_TYPE.PACKED_ROM_FILE

    if not os.path.isdir(out_path) and re.search(r"\.(o|romfs|rom|brom|vwr|bin|img)$", out_path, re.IGNORECASE) != None:
        out_type = PATH_TYPE.PACKED_ROM_FILE

    level1_path = None
    if not no_matryoshka:
        if level1_path == None:
            level1_path = "level1.bin"

    if in_type == PATH_TYPE.PACKED_ROM_FILE and out_type == PATH_TYPE.UNPACKED_FOLDER:
        if out_file_type == IMAGE_TYPE.ROM_BLOCKS or is_rom_blocks:
            if not silent:
                print("ROM Block Builder")

            rom_block_build_type = build_meta.detect(in_path)
            in_type = None
            if rom_block_build_type != None and "image_type" in rom_block_build_type:
                in_type = rom_block_build_type["image_type"]

            block_file_extension = ".rom"
            block_size = 0x10000
            address_base = 0x00000000
            header_version = BLOCK_HEADER_VERSION.VER2
            compression_type = BLOCK_COMPRESSION_TYPE.BSTR
            signature_type = BLOCK_SIGNATURE_TYPE.PROD
            message_templates = []

            if in_type == IMAGE_TYPE.COMPRESSED_BOOTROM or in_type == IMAGE_TYPE.ORIG_CLASSIC_BOOTROM:
                block_file_extension = ".brom"
                address_base = 0x01

            if rom_block_address_base != None:
                address_base = rom_block_address_base
            else:
                if in_type == IMAGE_TYPE.COMPRESSED_BOOTROM or in_type == IMAGE_TYPE.ORIG_CLASSIC_BOOTROM:
                    address_base = 0xbfc00000
                elif in_type == IMAGE_TYPE.ORIG_CLASSIC_BOX:
                    address_base = 0xbf000000
                else:
                    address_base = 0x00000000

            if rom_block_size == None:
                rom_block_size = 0x20000
            
            block_size = rom_block_size

            if rom_block_header_version != None:
                header_version = rom_block_header_version
            else:
                if in_type == IMAGE_TYPE.ORIG_CLASSIC_BOX or in_type == IMAGE_TYPE.ORIG_CLASSIC_BOOTROM:
                    header_version = BLOCK_HEADER_VERSION.VER1
                else:
                    header_version = BLOCK_HEADER_VERSION.VER2

            if rom_block_size == 0:
                compression_type = BLOCK_COMPRESSION_TYPE.BSTR
                block_size = 0x10000 # 64k or better
            elif rom_block_compression_type != None:
                compression_type = rom_block_compression_type
            else:
                compression_type = BLOCK_COMPRESSION_TYPE.BEST

            if rom_block_signature_type != None:
                signature_type = rom_block_signature_type
            else:
                signature_type = BLOCK_SIGNATURE_TYPE.PROD

            if rom_block_message != None:
                if os.path.isfile(rom_block_message):
                    with open(rom_block_message) as f:
                        message_templates = [line.rstrip() for line in f]
                else:
                    message_templates = [rom_block_message]
                pass
            else:
                message_templates = []

            rom_blocks.unpack(in_path, out_path, silent, block_file_extension, block_size, address_base, header_version, compression_type, signature_type, message_templates)
        else:
            process_file_to_folder(in_path, template_path, level1_path, out_path, silent, no_matryoshka, no_autodisk, no_data_section, no_romfs, no_nk, no_nk_registry, no_template)
    elif in_type == PATH_TYPE.UNPACKED_FOLDER and out_type == PATH_TYPE.PACKED_ROM_FILE:
        if out_file_type == IMAGE_TYPE.ROM_BLOCKS or is_rom_blocks or (not is_build_folder and rom_blocks.count_rom_parts(in_path) > 0):
            rom_blocks.pack(in_path, out_path, silent)
        else:
            process_folder_to_file(in_path, template_path, level1_path, out_path, out_file_type, silent, no_matryoshka, no_autodisk, no_data_section, no_romfs, no_nk, no_nk_registry, no_template, level0_data_path, level1_data_path, level1_lzj_version, autodisk_path)
    elif in_type == PATH_TYPE.PACKED_ROM_FILE and out_type == PATH_TYPE.PACKED_ROM_FILE:
        process_file_to_file(in_path, template_path, level1_path, out_path, out_file_type, silent, no_matryoshka, no_autodisk, no_data_section, no_romfs, no_nk, no_nk_registry, no_template, level0_data_path, level1_data_path, level1_lzj_version, autodisk_path)
    elif in_type == PATH_TYPE.UNPACKED_FOLDER and out_type == PATH_TYPE.UNPACKED_FOLDER and (out_file_type == IMAGE_TYPE.ROM_BLOCKS or is_rom_blocks or (not is_build_folder and rom_blocks.count_rom_parts(in_path) > 0)):
        tmp_dump_path = tempfile.mktemp()

        rom_blocks.pack(in_path, tmp_dump_path, silent)
        process_file_to_folder(tmp_dump_path, template_path, level1_path, out_path, silent, no_matryoshka, no_autodisk, no_data_section, no_romfs, no_nk, no_nk_registry, no_template)

        if tmp_dump_path != None and os.path.isfile(tmp_dump_path):
            os.remove(tmp_dump_path)
    else:
        raise Exception("Unknown dump method. in_type=" + str(in_type) + ", out_type=" + str(out_type) + ". Supported: image file to image folder, image folder to image file, image file to image file, rom upgrade block folder to image folder")

def main():
    allowed_output_types = [
        IMAGE_TYPE.VIEWER,
        IMAGE_TYPE.VIEWER_SCRAMBLED,
        IMAGE_TYPE.DREAMCAST,
        IMAGE_TYPE.BOX,
        IMAGE_TYPE.COMPRESSED_BOX,
        IMAGE_TYPE.COMPRESSED_BOOTROM,
        IMAGE_TYPE.ROM_BLOCKS
    ]

    allowed_block_signature_types = [
        str(BLOCK_SIGNATURE_TYPE.NONE),
        str(BLOCK_SIGNATURE_TYPE.TEST),
        str(BLOCK_SIGNATURE_TYPE.PROD),
        str(BLOCK_SIGNATURE_TYPE.DIAG)
    ]

    allowed_block_compression_types = [
        str(BLOCK_COMPRESSION_TYPE.LZSS),
        str(BLOCK_COMPRESSION_TYPE.DEFLATE)
    ]

    allowed_block_header_types = [
        str(BLOCK_HEADER_VERSION.VER1),
        str(BLOCK_HEADER_VERSION.VER2)
    ]

    allowed_lzj_versions = [
        str(LZJ_VERSION.VERSION1),
        str(LZJ_VERSION.VERSION2)
    ]

    description = "WebTV ROM Tool (Rommy) v1.0.0: "
    description += "This tool allows you to unpack and repack build images. It unpacks and packs ROMFS files, Autodisk files, CompressFS files, and UltimateTV NK.nb files. It supports all approm and bootrom images besides the classic bootrom and any diag-type builds. It also supports both raw and scrambled ROMFS files used in the WebTV viewer and the WEBTV.ROM found in the WebTV Dreamcast disk."

    epilog = "Special thanks to: Zefie, Outa, MattMan, and others in the WebTV hacking community! Have a --farted day!"

    ap = argparse.ArgumentParser(description=description, epilog=epilog)
    
    ap.add_argument('--info', action='store_true',
                    help="Attempt to display information about the input path.")

    ap.add_argument('--list', action='store_true',
                    help="Same as --info")

    ap.add_argument('--fixcs', action='store_true',
                    help="Fixes the code in an approm file.")

    ap.add_argument('--silent', '-q', action='store_true',
                    help="Don't print anything unless it's a fatal exception. --info ignores this.")

    ap.add_argument('--template-image-file', '-0', type=str,
                    help="When building an image file from a folder, we need an image file to get the build sections. Typically we use the OUT_PATH but this allows you to specify a separate image file.")

    ap.add_argument('--no-matryoshka', action='store_true',
                    help="Don't create or extract deeper compressed images. Compressed images inside images are used in bootroms images and LC2.5 and BPS approm images.")

    ap.add_argument('--no-onion', action='store_true',
                    help="Identical to --no-matryoshka")

    ap.add_argument('--no-autodisk', action='store_true',
                    help="Don't create or extract autodisk data.")

    ap.add_argument('--no-data-section', action='store_true',
                    help="Don't create or extract build '.data' section.")

    ap.add_argument('--no-romfs', action='store_true',
                    help="Don't create or extract build ROMFS. For UTV builds, this applies to the ComrpessFS images.")

    ap.add_argument('--no-compressfs', action='store_true',
                    help="Same as --no-romfs")

    ap.add_argument('--no-nk', action='store_true',
                    help="Don't create or extract of the UTV nk.nb file.")

    ap.add_argument('--no-nk-registry', action='store_true',
                    help="Don't further create or extract the UTV nk.nb registry file.")

    ap.add_argument('--rom-blocks', '-b', action='store_true',
                    help="Specify the input or output as rom upgrade block (part/chunk) files.")

    ap.add_argument('--rom-block-size', type=int,
                    help="The block size (in bytes) used for each upgrade block file. A smaller size will mean more block files. Rommy defaults to 131072. Set this to 0 for best-fit variable sizes (65536 and up); Rommy choses the size that compresses best. WNI used a fixed size of 131072 for all boxes except the UTV which was fixed at 65536.")

    ap.add_argument('--rom-block-address-base', type=int,
                    help="The base address to use when generating the ROM upgrade blocks. Default is 0x00000000 for LC2 and up approms, 0xbfc00000 for all bootroms and 0xbf000000 for original classic approm builds (bf0app).")

    ap.add_argument('--rom-block-header-version', type=str,
                    help="Use a specific ROM upgrade block header. The default is to use VER1 for original classic builds and VER2 for every other build. Allowed types: " + ", ".join(allowed_block_header_types))

    ap.add_argument('--rom-block-compression-type', type=str,
                    help="The ROM upgrade block compression to use. The best available is selected by default. Available: " + ", ".join(allowed_block_compression_types))

    ap.add_argument('--rom-block-signature-type', type=str,
                    help="The ROM upgrade block signature to use. The default is PROD. Available: " + ", ".join(allowed_block_signature_types))

    ap.add_argument('--rom-block-message', type=str,
                    help="Specify the ROM upgrade block message template. Either text or in a file path. You can have a different message per block on each line of a file. If the block index goes beyond the lines of the file, we will use the last line repeately. A message can't be more than 32 characters long. Replacements: {index}=block index, {total}=total # of blocks, {recv_data_size}=data sent, {total_data_size}=total data size, {current_block_size}=current block size, {name}=block file name")

    ap.add_argument('--out-type', '-t', type=str,
                    help="Specify an output image time. Only used if the output is a file and not a folder. If this is not used we will use the dt.json file, template file or file name to determine the output type. Allowed types: " + ", ".join(allowed_output_types))

    ap.add_argument('--level1-path', '-1', action='store_true',
                    help="Path to a level1 image to use when creating a new matryoshka build image. Will use details found in input directory otherwise. This is incompatible with --no-matryoshka.")

    ap.add_argument('--level0-data-path', action='store_true',
                    help="Path to a file containing the contents of the level0 .data section to use when creating a build image. Will use details found in input directory otherwise. This is incompatible with --no-data-section.")

    ap.add_argument('--level1-data-path', action='store_true',
                    help="Path to a file containing the contents of the level1 .data section to use when creating a build image. Will use details found in input directory otherwise. This is incompatible with --no-data-section.")

    ap.add_argument('--level1-lzj-version', type=str,
                    help="Specify the lzj version used when creating a compressed box (BPS and LC2.5) image. Available: " + ", ".join(allowed_lzj_versions))

    ap.add_argument('--autodisk-path', action='store_true',
                    help="Path to a folder containing the files to use when creating a build image. Will use details found in input directory otherwise. This is incompatible with --no-autodisk.")

    ap.add_argument('--no-template', action='store_true',
                    help="Don't build with a template. Only ROMFS image files can be built without a template.")

    ap.add_argument('--farted', '-f', action='store_true',
                    help="Let 'er rip a lovely one!")

    ap.add_argument('IN_PATH', type=str,
                    help="File path to the ROM data. Can be an approm image, a bootrom image, a ROMFS image, ROM upgrade block folder or a folder that was previous unpacked with this tool.")

    ap.add_argument('OUT_PATH', type=str, nargs='?',
                    help="File path to build to. This program will attempt to build a packed ROM image file if a folder is passed as an input OR if the output path is a file or ends in .o, .romfs, .rom, .brom, .vwr, .bin or .img. Otherwise, an unpack is attempted into a folder.")

    arg = ap.parse_args()

    silent = not arg.info and arg.silent 

    if arg.list:
        arg.info = arg.list

    if arg.no_onion:
        arg.no_matryoshka = True

    if arg.no_compressfs:
        arg.no_romfs = True

    out_type = None
    if arg.out_type != None:
        _out_type = arg.out_type.upper()

        if not _out_type in iter(IMAGE_TYPE) or not IMAGE_TYPE(_out_type) in allowed_output_types:
            raise Exception("Output image file type '" + _out_type + "' is not known. Allowed types: " + ", ".join(allowed_output_types))
        else:
            out_type = IMAGE_TYPE(_out_type)

    
    is_build_folder = (os.path.isfile(arg.IN_PATH + "/dt.json") and os.path.isfile(arg.IN_PATH + "/template.o") and os.path.isfile(arg.IN_PATH + "/level1.o"))

    if arg.OUT_PATH != None:
        rom_block_compression_type = None
        if arg.rom_block_compression_type != None:
            _rom_block_compression_type = arg.rom_block_compression_type.upper()

            if not BLOCK_COMPRESSION_TYPE.has_name(_rom_block_compression_type) or not _rom_block_compression_type in allowed_block_compression_types:
                raise Exception("Upgrade block compression type '" + _rom_block_compression_type + "' is not known. Allowed types: " + ", ".join(allowed_block_compression_types))
            else:
                rom_block_compression_type = BLOCK_COMPRESSION_TYPE[_rom_block_compression_type]

        rom_block_signature_type = None
        if arg.rom_block_signature_type != None:
            _rom_block_signature_type = arg.rom_block_signature_type.upper()

            if not BLOCK_SIGNATURE_TYPE.has_name(_rom_block_signature_type) or not _rom_block_signature_type in allowed_block_signature_types:
                raise Exception("Upgrade block signature type '" + _rom_block_signature_type + "' is not known. Allowed types: " + ", ".join(allowed_block_signature_types))
            else:
                rom_block_signature_type = BLOCK_SIGNATURE_TYPE[_rom_block_signature_type]

        rom_block_header_version = None
        if arg.rom_block_header_version != None:
            _rom_block_header_version = arg.rom_block_header_version.upper()

            if not BLOCK_HEADER_VERSION.has_name(_rom_block_header_version) or not _rom_block_header_version in allowed_block_header_types:
                raise Exception("Upgrade block header version '" + _rom_block_header_version + "' is not known. Allowed types: " + ", ".join(allowed_block_header_types))
            else:
                rom_block_header_version = BLOCK_HEADER_VERSION[_rom_block_header_version]

        level1_lzj_version = None
        if arg.level1_lzj_version != None:
            _level1_lzj_version = arg.level1_lzj_version.upper()

            if not LZJ_VERSION.has_name(_level1_lzj_version) or not _level1_lzj_version in allowed_lzj_versions:
                raise Exception("Upgrade block compression type '" + _level1_lzj_version + "' is not known. Allowed types: " + ", ".join(allowed_lzj_versions))
            else:
                level1_lzj_version = LZJ_VERSION[_level1_lzj_version]

        process(arg.IN_PATH, arg.template_image_file, arg.OUT_PATH, out_type, silent, arg.no_matryoshka, arg.no_autodisk, arg.no_data_section, arg.no_romfs, arg.no_nk, arg.no_nk_registry, arg.no_template, arg.level1_path, arg.level0_data_path, arg.level1_data_path, level1_lzj_version, arg.autodisk_path, arg.rom_blocks, is_build_folder, arg.rom_block_size, arg.rom_block_address_base, rom_block_header_version, rom_block_compression_type, rom_block_signature_type, arg.rom_block_message)
    elif arg.IN_PATH != None:
        if arg.fixcs:
            fixcs(arg.IN_PATH)
        else:
            info(arg.IN_PATH, arg.no_matryoshka, arg.no_autodisk, arg.no_data_section, arg.no_romfs, arg.no_nk, arg.no_nk_registry, (not is_build_folder or arg.rom_blocks))

    if arg.farted:
        do_fart()

main()
