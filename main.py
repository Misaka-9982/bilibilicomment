import os.path
import random
import requests
import json
import time
import jieba
import jieba.posseg
import re
import csv

import bv_av


class BilibiliCommentSpider:
    def __init__(self, vid: str, pagenum=1, delay=3, mode=3):
        if vid.isnumeric():  # 纯数字av号
            self.oid = int(vid)
        else:  # BV开头的bv号
            self.oid = bv_av.dec(vid)
        # self.delay = delay   # 爬取延迟随机范围
        self.mode = mode  # mode=3按热门，mode=2按时间
        self.pagenum = pagenum  # 爬取总页数
        self.url = 'https://api.bilibili.com/x/v2/reply/wbi/main?'
        self.headers = {'UserAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                                     'Chrome/104.0.5112.102 Safari/537.36 Edg/104.0.1293.63'}
        self.next = 0  # 评论页数第一页是0，后续在data: cursor: next中
        self.querystrparams = f'jsonp=jsonp&next={self.next}&type=1&oid={self.oid}&mode={self.mode}&plat=1'
        self.allpagedict = []  # 所有页的集合
        self.sortedcomment: list[dict] = []  # 主回复和子回复整理后分开存储
        self.vidname = None
        self.proxies = {'http': 'http://127.0.0.1:7890',
                      "https": "http://127.0.0.1:7890"}

    def get_basic_info(self):  # 获取标题等
        url = f'https://www.bilibili.com/video/av{self.oid}'
        res = requests.get(url, headers=self.headers, proxies=self.proxies)
        title = re.findall('<title data-vue-meta="true">(.*?)</title>', res.text)
        if len(title) == 0:
            title = re.findall('<html>.*?<title>(.*?)</title>', res.text)
        try:
            return title[0]
        except IndexError:
            return '[ERROR]未解析到视频名称'

    def request_json_dict(self):
        t1 = time.time()
        print(f'开始爬取评论   {time.asctime()}')
        for i in range(self.pagenum):
            t2 = time.time()
            print(f'正在爬取{i + 1}/{self.pagenum}页，已用时{t2 - t1:.2f}秒')
            try:
                res = requests.get(self.url, params=self.querystrparams, headers=self.headers, proxies=self.proxies)
            except (requests.exceptions.SSLError, requests.exceptions.ProxyError) as e:
                print(repr(e))
                exit('SSL/代理错误，请关闭代理或检查网络设置')
            except Exception as e:
                exit(f'未知错误！\n{repr(e)}')
            page_dict = json.loads(res.text)
            self.allpagedict.append(page_dict)
            try:
                self.next = page_dict['data']['cursor']['next']
            except KeyError:
                exit('未爬取到有效内容')
            self.querystrparams = f'jsonp=jsonp&next={self.next}&type=1&oid={self.oid}&mode={self.mode}&plat=1'
            time.sleep(random.uniform(1, 3))  # 随机间隔时间范围
        t2 = time.time()
        print(f'爬取结束，用时{t2 - t1:.2f}秒    {time.asctime()}')
        self.sortcomment()   # 整合评论
        return self.allpagedict

    def getpages(self, n) -> dict:  # 从0开始   # 一页20个主评论
        if n > self.pagenum:
            raise IndexError(f'第{n}页未抓取！')
        else:
            return self.allpagedict[n]

    # def getpagereplynums(self, page: dict):   # 统计传入页内容字典中，所有

    def users_level_ratio(self):
        start = input('是否进行用户等级比例分析？ 1、分析（默认） 2、不分析')
        if start == '2':
            return
        print('开始分析用户等级比例')
        time.sleep(3)
        levellist = [0] * 8  # 对应0-6闪电 八个等级
        for comment in self.sortedcomment:
            if comment['member']['is_senior_member'] == 1:
                levellist[7] += 1
            else:
                levellist[comment['member']['level_info']['current_level']] += 1

        print(
            f'level 0: {levellist[0]}\nlevel 1: {levellist[1]}\nlevel 2: {levellist[2]}\nlevel 3: {levellist[3]}\nlevel 4: '
            f'{levellist[4]}\nlevel 5: {levellist[5]}\nlevel 6: {levellist[6]}\nlevel 6+: {levellist[7]}\n'
            f'视频名称: {self.vidname}   AV{self.oid}\n  共计{sum(levellist)}位用户')
        print('爬取逻辑按热度排序') if self.mode == 3 else print('爬取逻辑按时间倒序')
        print(
            f'  0-4级占比{(sum(levellist[0:5]) / sum(levellist)) * 100:.2f}%   '
            f'5级及以上占比{(sum(levellist[5:]) / sum(levellist)) * 100:.2f}%   6级及以上占比{(sum(levellist[6:]) / sum(levellist)) * 100:.2f}%'
            f'   6+级占比{(levellist[7] / sum(levellist)) * 100:.2f}%')

    def remove_duplicate(self):
        print('开始去除复制粘贴评论')
        dup_dict = {}
        del_num = 0
        for num, comment in enumerate(self.sortedcomment):
            if comment['content']['message'] not in dup_dict:
                dup_dict[comment['content']['message']] = 1
            else:
                dup_dict[comment['content']['message']] += 1
                if dup_dict[comment['content']['message']] > 2:
                    # del self.sortedcomment[num]   这里不能使用索引num来删除，遍历中增删元素会导致索引变化错位，导致隐蔽的结果异常
                    self.sortedcomment.remove(comment)
                    del_num += 1
        print(f'去除完成，共去除{del_num}条重复评论，剩余{len(self.sortedcomment)}条评论')
        time.sleep(3)

    def words_frequency(self):
        start = input('是否进行高频词分析: 1、分析(默认) 2、不分析\n')
        if start == '2':
            return
        duplicate_remove = input('是否去除复制粘贴的评论？可能会导致评论较少（整句重复两次以上） 1、去除(默认) 2、不去除\n')
        if duplicate_remove != '2':
            self.remove_duplicate()
        print('开始分析词频')
        time.sleep(3)
        words_dict = {}
        stop_list = ['回复', '是', '个', '们', '怎么', '没有', '什么', '这']
        jump_sort = ['p', 'u', 'q', 'c', 'r']  # 按词性排除
        jump_flag = False  # 跳过b站表情标签
        print('正在计算高频词')
        for comment in self.sortedcomment:
            for word, sort in jieba.posseg.cut(comment['content']['message'], HMM=True):  # cut返回迭代器  HMM-词库外的新词分割
                if sort in jump_sort:
                    continue
                if word == '[' or jump_flag:  # 过滤b站表情
                    jump_flag = True
                    if word == ']':
                        jump_flag = False
                    continue

                if len(re.findall('.*[\u4e00-\u9fa5]{2,}.*', word)):  # 仅匹配中文且长度大于1
                    stop_flag = False
                    for stop_word in stop_list:   # 黑名单过滤
                        if stop_word in word:
                            stop_flag = True
                            break
                    if not stop_flag:
                        if word in words_dict:
                            words_dict[word] += 1
                        else:
                            words_dict[word] = 1

        rank = 10   # 切片左闭右开
        rank_in = input(f'分析完成，共{len(words_dict)}个关键词，需要展示前几名的高频词？(默认前10)\n')
        if rank_in.isnumeric():
            rank = int(rank_in)
        words_freq_list = sorted(words_dict.items(), key=lambda x: x[1], reverse=True)[:rank]
        print(f'前{rank}高频词: ')
        for num, word in enumerate(words_freq_list):
            print(f'{num+1}、{word[0]} - {word[1]}次')
        return words_freq_list

    def resortcomment(self):
        print('是否按点赞数从高到低排序评论，消除阿瓦隆权重影响？ 1、重排序')
        start = input()
        # 待完成
        self.sortedcomment.sort(key=lambda x: x.get('like'), reverse=True)
        return self.sortedcomment

    def sortcomment(self):  # 将主次回复同等级整合
        print('开始整合评论')
        for num in range(pagenum):
            page = self.getpages(num)
            if page.get('data').get('replies') is not None:  # 防止无回复时产生keyerror
                for mainreply in page['data']['replies']:  # 主回复
                    if mainreply.get('replies') is not None:
                        for subreply in mainreply['replies']:  # 子回复
                            self.sortedcomment.append(subreply)

                    del mainreply['replies']
                    self.sortedcomment.append(mainreply)

            else:
                print(f'第{num}页无评论！')
        print(f'共计{len(self.sortedcomment)}条评论')

    def save_as_csv(self):
        save = input('保存所有评论为csv格式输入y，否则n')
        if save == 'y':
            verbose = input(
                '\n选择内容详细程度（默认2，回车默认）:\n1、用户名+内容\n2、uid+用户名+性别+等级+时间+内容\n3、（暂未开发）\n')
            if verbose == '':
                verbose = 2
            elif verbose.isnumeric():
                verbose = int(verbose)

            n = 1  # 同名文件编号
            while os.path.isfile(f'{self.vidname}-{n}.csv'):
                n += 1
            # newline=''防止换行符转换错误
            with open(f'{self.vidname}-{n}.csv', 'w', newline='', encoding='utf_8_sig') as f:  # utf-8 BOM 否则excel无法识别
                writer = csv.writer(f)
                if verbose == 1:
                    writer.writerow(['用户名', '内容'])  # 表头
                    for comment in self.sortedcomment:
                        writer.writerow([comment['member']['uname'], comment['content']['message']])
                    print(f'已保存到{self.vidname}-{n}.csv')
                elif verbose == 2:
                    writer.writerow(['uid', '用户名', '性别', '等级', '发布时间', '内容'])
                    for comment in self.sortedcomment:
                        writer.writerow([comment['member']['mid'], comment['member']['uname'], comment['member']['sex'],
                                         comment['member']['level_info']['current_level'],
                                         time.asctime(time.localtime(comment['ctime'])),
                                         comment['content']['message']])
                    print(f'已保存到{self.vidname}-{n}.csv')
                elif verbose == 3:
                    print('暂未开发')

                else:
                    print('参数错误，默认无格式保存全部内容，可能保存失败')
                    for comment in self.sortedcomment:
                        try:
                            writer.writerow(comment.items)
                        except Exception as e:
                            print('未知错误！')
                            print(repr(e))
        else:
            print('\n爬取完成，未保存')

    def run(self):
        allpagedict = self.request_json_dict()
        self.vidname = self.get_basic_info()
        self.users_level_ratio()
        self.words_frequency()
        self.save_as_csv()


if __name__ == '__main__':
    print('b站视频评论区查询姬')
    vid = input('输入视频AV号（不带av前缀的纯数字）或BV号(带BV前缀): ')  # 判断流程在构造函数
    pagenum = int(input('输入需要抓取的页数: '))
    mode = int(input('输入数字选择评论排序模式：\n1、按热度排序(默认)\n2、按时间排序'))
    spider = BilibiliCommentSpider(vid=vid, pagenum=pagenum,
                                   mode=mode if mode == 2 else 3)  # vid为纯数字av号(int)或以BV开头的bv号(str)
    spider.run()
