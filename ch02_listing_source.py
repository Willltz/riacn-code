# coding: utf-8

import json
import threading
import time
import unittest
import urlparse
import uuid

QUIT = False

# 代码清单 2-1
# <start id="_1311_14471_8266"/>
def check_token(conn, token):
    return conn.hget('login:', token)   # 尝试获取并返回令牌对应的用户。
# <end id="_1311_14471_8266"/>


# 代码清单 2-2
# <start id="_1311_14471_8265"/>
def update_token(conn, token, user, item=None):
    # 获取当前时间戳。
    timestamp = time.time()
    # 维持令牌与已登录用户之间的映射。
    conn.hset('login:', token, user)
    # 记录令牌最后一次出现的时间。
    conn.zadd('recent:', token, timestamp)#zadd:将一个或多个成员元素及其分数值加入有序集中
    if item:
        # 记录用户浏览过的商品。
        conn.zadd('viewed:' + token, item, timestamp)
        # 移除旧的记录，只保留用户最近浏览过的25个商品。
        conn.zremrangebyrank('viewed:' + token, 0, -26)
# <end id="_1311_14471_8265"/>


# 代码清单 2-3
# <start id="_1311_14471_8270"/>
QUIT = False
LIMIT = 10000000

def clean_sessions(conn):#清理旧会话
    while not QUIT:
        # 找出目前已有令牌的数量。
        size = conn.zcard('recent:')#zcard用于计算集合中元素的数量
        # 令牌数量未超过限制，休眠并在之后重新检查。
        if size <= LIMIT:
            time.sleep(1)
            continue

        #  获取需要移除的令牌ID。
        end_index = min(size - LIMIT, 100)#最多移除100个
        #zrange返回有序集中，指定区间内的成员。成员的位置按分数值递增排序
        tokens = conn.zrange('recent:', 0, end_index-1)

        # 为那些将要被删除的令牌构建键名。
        session_keys = []
        for token in tokens:
            session_keys.append('viewed:' + token)

        # 移除最旧的那些令牌。
        conn.delete(*session_keys)#带*这种语法可以将一连串的多个参数传入函数
        #hdel:删除哈希表中一个或多个指定字段，不存在的字段将被忽略
        conn.hdel('login:', *tokens)
        #zrem:用于移除有序集中的一个或多个成员，不存在的成员将被忽略
        conn.zrem('recent:', *tokens)
# <end id="_1311_14471_8270"/>


# 代码清单 2-4
# <start id="_1311_14471_8279"/>
def add_to_cart(conn, session, item, count):#更新购物车
    if count <= 0:#count:订购某件商品的数量
        # 从购物车里面移除指定的商品。
        conn.hrem('cart:' + session, item) #hrem??? or hdel?
    else:
        # 将指定的商品添加到购物车。
        conn.hset('cart:' + session, item, count) 
# <end id="_1311_14471_8279"/>


# 代码清单 2-5
# <start id="_1311_14471_8271"/>
def clean_full_sessions(conn):
    while not QUIT:
        size = conn.zcard('recent:')
        if size <= LIMIT:
            time.sleep(1)
            continue

        end_index = min(size - LIMIT, 100)
        sessions = conn.zrange('recent:', 0, end_index-1)

        session_keys = []
        for sess in sessions:
            session_keys.append('viewed:' + sess)
            session_keys.append('cart:' + sess)   # 新增加的这行代码用于删除旧会话对应用户的购物车。

        conn.delete(*session_keys)
        conn.hdel('login:', *sessions)
        conn.zrem('recent:', *sessions)
# <end id="_1311_14471_8271"/>


# 代码清单 2-6
# <start id="_1311_14471_8291"/>
def cache_request(conn, request, callback):
    # 对于不能被缓存的请求，直接调用回调函数。
    if not can_cache(conn, request):
        return callback(request)

    # 将请求转换成一个简单的字符串键，方便之后进行查找。
    page_key = 'cache:' + hash_request(request) 
    # 尝试查找被缓存的页面。
    content = conn.get(page_key)

    if not content:
        # 如果页面还没有被缓存，那么生成页面。
        content = callback(request)
        # 将新生成的页面放到缓存里面 300 seconds。
        conn.setex(page_key, content, 300)#setex:为指定的key设置值及其过期时间。

    # 返回页面。
    return content
# <end id="_1311_14471_8291"/>


# 代码清单 2-7
# <start id="_1311_14471_8287"/>
def schedule_row_cache(conn, row_id, delay):
    # 先设置数据行的延迟值。
    conn.zadd('delay:', row_id, delay) 
    # 立即缓存数据行。
    conn.zadd('schedule:', row_id, time.time()) 
# <end id="_1311_14471_8287"/>


# 代码清单 2-8
# <start id="_1311_14471_8292"/>
def cache_rows(conn):
    while not QUIT:
        # 尝试获取下一个需要被缓存的数据行以及该行的调度时间戳，
        # 命令会返回一个包含零个或一个元组（tuple）的列表。
        next = conn.zrange('schedule:', 0, 0, withscores=True) 
        now = time.time()
        if not next or next[0][1] > now:
            # 暂时没有行需要被缓存，休眠50毫秒后重试。
            time.sleep(.05) 
            continue

        row_id = next[0][0]
        # 获取下一次调度前的延迟时间。
        delay = conn.zscore('delay:', row_id)#zscore:返回有序集中成员的分数值
        if delay <= 0:
            # 不必再缓存这个行，将它从缓存中移除。
            conn.zrem('delay:', row_id) 
            conn.zrem('schedule:', row_id)
            conn.delete('inv:' + row_id)
            continue

        # 读取数据行。
        row = Inventory.get(row_id)
        # 更新调度时间并设置缓存值。
        conn.zadd('schedule:', row_id, now + delay)         
        conn.set('inv:' + row_id, json.dumps(row.to_dict())) 
# <end id="_1311_14471_8292"/>


# 代码清单 2-9
# <start id="_1311_14471_8298"/>
def update_token(conn, token, user, item=None):
    timestamp = time.time()
    conn.hset('login:', token, user)
    conn.zadd('recent:', token, timestamp)
    if item:
        conn.zadd('viewed:' + token, item, timestamp)
        #移除有序集中指定排名区间的所有成员
        conn.zremrangebyrank('viewed:' + token, 0, -26)
        #zincrby:对有序集合中指定成员的分数加上增量increment
        conn.zincrby('viewed:', item, -1)        # 这行代码是新添加的。
# <end id="_1311_14471_8298"/>


# 代码清单 2-10
# <start id="_1311_14471_8288"/>
def rescale_viewed(conn):
    while not QUIT:
        # 删除所有排名在20000名之后的商品。
        conn.zremrangebyrank('viewed:', 0, -20001) 
        # 将浏览次数降低为原来的一半 #zinterstore:计算给定的一个或多个有序集的交集
        conn.zinterstore('viewed:', {'viewed:': .5}) 
        # 5分钟之后再执行这个操作。
        time.sleep(300) 
# <end id="_1311_14471_8288"/>


# 代码清单 2-11
# <start id="_1311_14471_8289"/>
def can_cache(conn, request):
    # 尝试从页面里面取出商品ID。
    item_id = extract_item_id(request)
    # 检查这个页面能否被缓存以及这个页面是否为商品页面。
    if not item_id or is_dynamic(request):
        return False
    # 取得商品的浏览次数排名。#zrank:返回有序集中指定成员的排名(递增顺序)
    rank = conn.zrank('viewed:', item_id)
    # 根据商品的浏览次数排名来判断是否需要缓存这个页面。
    return rank is not None and rank < 10000 
# <end id="_1311_14471_8289"/>


#--------------- 以下是用于测试代码的辅助函数 --------------------------------

def extract_item_id(request):
    #urlparse模块主要是把url拆分为6部分，并返回元组
    #(scheme, netloc, path, parameters, query, fragment)
    parsed = urlparse.urlparse(request)
    #urlparse.parse_qs返回字典,urlparse.parse_qsl返回列表
    query = urlparse.parse_qs(parsed.query)
    return (query.get('item') or [None])[0]

def is_dynamic(request):
    parsed = urlparse.urlparse(request)
    query = urlparse.parse_qs(parsed.query)
    return '_' in query

def hash_request(request):
    return str(hash(request))

class Inventory(object):
    def __init__(self, id):
        self.id = id

    @classmethod
    def get(cls, id):
        return Inventory(id)

    def to_dict(self):
        return {'id':self.id, 'data':'data to cache...', 'cached':time.time()}

#unittest.TestCase：TestCase类，所有测试用例类继承的基本类
class TestCh02(unittest.TestCase):
    def setUp(self):#用于测试用例执行前的初始化工作,如建立数据库连接并进行初始化
        import redis
        #完整格式:redis.Redis的init()函数定义：__init__(self, host='localhost', 
        #port=6379, db=0, password=None, socket_timeout=None, connection_pool=None, 
        #charset='utf-8', errors='strict', decode_responses=False, unix_socket_path=None)
        #常用格式:redis.Redis(host="localhost",port=6379,db=0),db=0,就是选择操作0号数据库,redis默认有16个数据库,在conf里可以配置
        self.conn = redis.Redis(db=15)#创建redis连接实例,实现python操作redis!!!!

    def tearDown(self):#用于测试用例执行之后的善后工作,如关闭数据库连接,关闭浏览器
        conn = self.conn
        to_del = ( #keys:用于搜索满足指定匹配模式的键
            conn.keys('login:*') + conn.keys('recent:*') + conn.keys('viewed:*') +
            conn.keys('cart:*') + conn.keys('cache:*') + conn.keys('delay:*') + 
            conn.keys('schedule:*') + conn.keys('inv:*'))
        if to_del:
            self.conn.delete(*to_del)
        del self.conn
        global QUIT, LIMIT
        QUIT = False
        LIMIT = 10000000
        print
        print

    #(1)具体的测试用例，一定要以test开头
    def test_login_cookies(self):
        conn = self.conn
        global LIMIT, QUIT
        token = str(uuid.uuid4())#基于随机数生成uuid

        update_token(conn, token, 'username', 'itemX')
        print "We just logged-in/updated token:", token
        print "For user:", 'username'
        print

        print "What username do we get when we look-up that token?"
        r = check_token(conn, token)
        print r
        print
        self.assertTrue(r)#测试该表达式是真值


        print "Let's drop the maximum number of cookies to 0 to clean them out"
        print "We will start a thread to do the cleaning, while we stop it later"
        ##################创建一个线程执行清理工作!!!!####################
        LIMIT = 0
        #threading.Thread:第一个参数是线程函数变量，第二个参数args是一个数组变量参数，如果只传递一个值，就只需要i, 
        #如果需要传递多个参数，那么还可以继续传递下去其他的参数，其中的逗号不能少，少了就不是数组了，就会出错。
        #threading.Thread类的初始化函数原型：
        #def __init__(self, group=None, target=None, name=None, args=(), kwargs={})
        t = threading.Thread(target=clean_sessions, args=(conn,))
        t.setDaemon(1) # to make sure it dies if we ctrl+C quit
        t.start()
        time.sleep(1)
        QUIT = True
        time.sleep(2)
        if t.isAlive():#判断线程是否是激活的（alive）
            raise Exception("The clean sessions thread is still alive?!?")

        s = conn.hlen('login:')
        print "The current number of sessions still available is:", s
        self.assertFalse(s)#测试该表达式是false

    #(2)具体的测试用例，一定要以test开头
    def test_shoppping_cart_cookies(self):
        conn = self.conn
        global LIMIT, QUIT
        token = str(uuid.uuid4())

        print "We'll refresh our session..."
        update_token(conn, token, 'username', 'itemX')
        print "And add an item to the shopping cart"
        add_to_cart(conn, token, "itemY", 3)
        r = conn.hgetall('cart:' + token)
        print "Our shopping cart currently has:", r
        print

        self.assertTrue(len(r) >= 1)

        print "Let's clean out our sessions and carts"
        LIMIT = 0
        t = threading.Thread(target=clean_full_sessions, args=(conn,))
        t.setDaemon(1) # to make sure it dies if we ctrl+C quit
        t.start()
        time.sleep(1)
        QUIT = True
        time.sleep(2)
        if t.isAlive():
            raise Exception("The clean sessions thread is still alive?!?")

        r = conn.hgetall('cart:' + token)
        print "Our shopping cart now contains:", r

        self.assertFalse(r)

    #(3)具体的测试用例，一定要以test开头
    def test_cache_request(self):
        conn = self.conn
        token = str(uuid.uuid4())

        #回调函数,不由实现方直接调用，而是在特定条件发生时由另一方调用
        def callback(request):
            return "content for " + request

        update_token(conn, token, 'username', 'itemX')
        url = 'http://test.com/?item=itemX'
        print "We are going to cache a simple request against", url
        result = cache_request(conn, url, callback)
        print "We got initial content:", repr(result)#将任意值转为字符串
        print

        self.assertTrue(result)

        print "To test that we've cached the request, we'll pass a bad callback"
        result2 = cache_request(conn, url, None)
        print "We ended up getting the same response!", repr(result2)

        self.assertEquals(result, result2)

        self.assertFalse(can_cache(conn, 'http://test.com/'))
        self.assertFalse(can_cache(conn, 'http://test.com/?item=itemX&_=1234536'))

    #(4)具体的测试用例，一定要以test开头
    def test_cache_rows(self):
        import pprint
        conn = self.conn
        global QUIT
        
        print "First, let's schedule caching of itemX every 5 seconds"
        schedule_row_cache(conn, 'itemX', 5)
        print "Our schedule looks like:"
        s = conn.zrange('schedule:', 0, -1, withscores=True)
        pprint.pprint(s)
        print "test:",s
        self.assertTrue(s)

        print "We'll start a caching thread that will cache the data..."
        t = threading.Thread(target=cache_rows, args=(conn,))
        t.setDaemon(1)
        t.start()

        time.sleep(1)
        print "Our cached data looks like:"
        r = conn.get('inv:itemX')
        print repr(r)
        self.assertTrue(r)
        print
        print "We'll check again in 5 seconds..."
        time.sleep(5)
        print "Notice that the data has changed..."
        r2 = conn.get('inv:itemX')
        print repr(r2)
        print
        self.assertTrue(r2)
        self.assertTrue(r != r2)

        print "Let's force un-caching"
        schedule_row_cache(conn, 'itemX', -1)
        time.sleep(1)
        r = conn.get('inv:itemX')
        print "The cache was cleared?", not r
        print
        self.assertFalse(r)

        QUIT = True
        time.sleep(2)
        if t.isAlive():
            raise Exception("The database caching thread is still alive?!?")

    # We aren't going to bother with the top 10k requests are cached, as
    # we already tested it as part of the cached requests test.

if __name__ == '__main__':

    #unittest:python单元测试模块,对象是函数
    unittest.main()
