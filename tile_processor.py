#!/usr/bin/python
# -*- coding: UTF-8 -*-

import sys
import numpy
from osgeo import gdal, osr
import math
import os
import time
gdal.UseExceptions()
# os.environ['PROJ_LIB'] = os.path.dirname(sys.argv[0]) + '/proj'

class Processor:
    size = 256

    def __init__(self, argv):
        if len(argv) < 3:
            print("用法： python tile_processor.py source_file zoom1,zoom2,zoom3")
            print("或分别输入 tif 文件路径和要生成的切片等级(以英文输入状态下的逗号分隔，如 18,19)")
            in_path = input("输入 tif 文件路径：")
            in_list = input("输入要生成的切片等级：")
        else:
            in_path = argv[1]
            in_list = argv[2]
        zoom_list = []
        for z in in_list.split(","):
            zoom_list.append(int(z))
        self.zoom_list = zoom_list
        self.timestamp = int(round(time.time() * 1000))
        self.readTif(in_path)

    def setZoom(self, zoom):
        self.zoom = zoom

    def readTif(self, file_path):
        self.dirname = os.path.dirname(file_path)
        try:
            dataset = gdal.Open(file_path)
        except RuntimeError:
            print(f'没有找到文件：{file_path}')
            input("按任意键退出程序")
            sys.exit(1)
        if dataset == None:
            print(f'无法打开文件：{file_path}')
            input("按任意键退出程序")
            sys.exit(1)
        # 宽度，栅格矩阵的列数
        self.im_width = dataset.RasterXSize
        # 高度，栅格矩阵的行数
        self.im_height = dataset.RasterYSize
        # 波段数，蓝、绿、红、近红外
        self.im_bands = dataset.RasterCount
        # 获取仿射矩阵信息
        self.im_geotrans = dataset.GetGeoTransform()
        # 获取投影信息
        self.im_proj = dataset.GetProjection()
        # 获取坐标系 EPSG 代号
        proj_sr = osr.SpatialReference(wkt = self.im_proj)
        proj_sr_epsg = proj_sr.GetAttrValue('AUTHORITY', 1)
        # 左上经度
        lt_lon = self.im_geotrans[0]
        # 左上纬度
        lt_lat = self.im_geotrans[3]
        # 右下经度
        rd_lon = self.im_geotrans[0] + self.im_width * self.im_geotrans[1] + self.im_height * self.im_geotrans[2]
        # 右下纬度
        rd_lat = self.im_geotrans[3] + self.im_width * self.im_geotrans[4] + self.im_height * self.im_geotrans[5]

        if proj_sr_epsg != '4490':
            print(f'当前文件坐标参照系为 EPSG:{proj_sr_epsg}，请使用 EPSG:4490 坐标系')
            input("按任意键退出程序")
            sys.exit(1)
        else:
            # TODO: 坐标系转换
            pass
        self.lt_lon = lt_lon
        self.lt_lat = lt_lat
        self.rd_lon = rd_lon
        self.rd_lat = rd_lat
        # 获取数据类型
        band1 = dataset.GetRasterBand(1)
        self.data_type = band1.DataType
        self.dataset = dataset

    def getRowCol(self, lon, lat, zoom):
        row_span, col_span = self.getSpan(zoom)
        row = (90 - lat) / row_span
        col = (lon - (-180)) / col_span
        return row, col

    def getSpan(self, zoom):
        row_span = 180 / math.pow(2, zoom -1)
        col_span = 360 / math.pow(2, zoom)
        return row_span, col_span

    def getSize(self, zoom):
        row_span, col_span = self.getSpan(zoom)
        d_lon = math.fabs(self.lt_lon - self.rd_lon)
        d_lat = math.fabs(self.lt_lat - self.rd_lat)
        new_width = d_lon / col_span * self.size
        new_height = d_lat / row_span * self.size
        width_scale = new_width / self.im_width
        height_scale = new_height / self.im_height
        return new_width, new_height, width_scale, height_scale

    def run(self):
        print(f'-------- 处理 {self.zoom} 级切片 --------')
        target_dir = f'{self.zoom}_{self.timestamp}'
        target_dir_path = os.path.join(self.dirname, target_dir)
        print(f'{self.zoom} 级切片将保存在 {target_dir_path} 目录下')
        if not os.path.exists(target_dir_path):
            os.mkdir(target_dir_path)
        row_span, col_span = self.getSpan(self.zoom)
        width, height, width_scale, height_scale = self.getSize(self.zoom)
        width = int(width)
        height = int(height)
        geotrans = list(self.im_geotrans)
        # 将像元宽度变为原来的 scale 倍
        geotrans[1] = geotrans[1] / width_scale
        # 将像元高度变为原来的 scale 倍
        geotrans[5] = geotrans[5] / height_scale
        target = self.dataset.GetDriver().Create(
            os.path.join(target_dir_path, f'result_{self.zoom}.tif'),
            xsize = width,
            ysize = height,
            bands = self.im_bands,
            eType = self.data_type
        )
        target.SetProjection(self.im_proj)
        target.SetGeoTransform(geotrans)
        for i in range(1, self.im_bands + 1):
            data = self.dataset.GetRasterBand(i).ReadAsArray(buf_xsize = width, buf_ysize = height)
            out_band = target.GetRasterBand(i)
            out_band.SetNoDataValue(self.dataset.GetRasterBand(i).GetNoDataValue())
            out_band.WriteArray(data)
            out_band.FlushCache()
            out_band.ComputeBandStats(False)
            print(f'result_{self.zoom}.tif : 写入 {i} 波段')

        print(f'result_{self.zoom}.tif : 写入完成')
        print('开始切片……')
        lt_row, lt_col = self.getRowCol(self.lt_lon, self.lt_lat, self.zoom)
        rd_row, rd_col = self.getRowCol(self.rd_lon, self.rd_lat, self.zoom)
        lt_row = math.floor(lt_row)
        lt_col = math.floor(lt_col)
        rd_row = math.ceil(rd_row)
        rd_col = math.ceil(rd_col)
        lt_lon = lt_col * col_span - 180
        lt_lat = 90 - (lt_row * row_span)
        x_offset = (self.lt_lon - lt_lon) / col_span * self.size * -1
        y_offset = (lt_lat - self.lt_lat) / row_span * self.size * -1
        print(f'{self.zoom} 级下的初始偏移为：({x_offset}, {y_offset})')
        for c in range(0, rd_col - lt_col):
            for r in range(0, rd_row - lt_row):
                current_col = lt_col + c
                current_row = lt_row + r
                current_file_path = os.path.join(target_dir_path, f'{current_col}_{current_row}.png')
                gdal.Translate(
                    current_file_path,
                    target,
                    format = 'png',
                    srcWin = [x_offset + c * self.size, y_offset + r * self.size, self.size, self.size]
                )
                print(f'生成切片 {current_file_path}')
        del target

def main():
    process = Processor(sys.argv)
    for zoom in process.zoom_list:
        process.setZoom(zoom)
        process.run()
    del process
    print("切片完成")
    input("按任意键退出程序")
    return 0

if __name__ == '__main__':
    sys.exit(main())
