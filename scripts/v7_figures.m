function v7_figures(root,skillRoot)
% V7: MATLAB source figures at manuscript size, using verified trajectories.
cd(root);addpath(fullfile(skillRoot,'references','roles','编程手','scripts'));
D=load('artifacts/v7/figure_data.mat');out='figures/v7';if ~isfolder(out),mkdir(out);end
C.grid=hex('#4D779B');C.soc=hex('#8074C8');C.price=hex('#8D2F25');C.base=hex('#9D9EA3');
C.emergency=hex('#992224');C.orange=hex('#EF8B67');C.gold=hex('#F0C284');C.pale=hex('#A8CBDF');
% The shared constraints persist; only information and contract permissions grow.
f=fig(3.45);a=axes(f,'Position',[.02 .03 .96 .93]);axis(a,[0 100 0 100]);axis(a,'off');hold(a,'on');
box(a,[2 81 96 15],{'共同基础：能量平衡 · 储能递推 · 容量与功率约束','决策输出：计划购电、充放电、紧急购电与实际费用'},C.grid);
ys=[63 44 25 6]; labs={'问题一','问题二','问题三','问题四'};
inputs={{'已知供需与分时电价'},{'新增：供需预测误差'},{'新增：日内预报与调单'},{'新增：价格变化与未知性'}};
acts={{'确定性线性规划'},{'风险校准 + 库存价值'},{'滚动优化 + 可调单价值'},{'预测价格驱动日前 / 滚动策略'}};
for k=1:4
 box(a,[2 ys(k) 14 13],labs(k),C.grid);box(a,[20 ys(k) 34 13],inputs{k},C.base);box(a,[59 ys(k) 39 13],acts{k},C.soc);
 arrow(a,[16 ys(k)+6.5],[20 ys(k)+6.5]);arrow(a,[54 ys(k)+6.5],[59 ys(k)+6.5]);
 if k<4,arrow(a,[78 ys(k)],[78 ys(k+1)+13]);end
end
saveout(f,out,'modeling_overview');

% Cost bridge includes reoptimization: the efficiency penalty is a system effect.
f=fig(3.2);a=ax(f,[.095 .24 .48 .60]);panel(a,'a','储能收益与效率代价');v=D.q1_waterfall(:);ys=[v(1),v(1)-v(2),v(3)-v(2),v(3)];
bottom=[0,v(2),v(2),0];colors=[C.base;C.grid;C.orange;C.soc];
for k=1:4,patch(a,k+[-.29 .29 .29 -.29],[bottom(k) bottom(k) bottom(k)+ys(k) bottom(k)+ys(k)],colors(k,:),'EdgeColor','none');end
plot(a,[1.29 1.71],[v(1) v(1)],':','Color',C.base);plot(a,[2.29 2.71],[v(2) v(2)],':','Color',C.base);plot(a,[3.29 3.71],[v(3) v(3)],':','Color',C.base);
labels={sprintf('%.3f',v(1)),sprintf('−%.3f',ys(2)),sprintf('+%.3f',ys(3)),sprintf('%.3f',v(3))};
for k=1:4,text(a,k,bottom(k)+ys(k)+.12,labels{k},'HorizontalAlignment','center','FontSize',8);end
set(a,'XLim',[.5 4.5],'YLim',[0 5.55],'XTick',1:4,'XTickLabel',{'无储能','无损储能收益','效率代价','实际储能'},'FontSize',7.5);ylabel(a,'最优日费用 / 万元');
text(a,.54,5.32,'净节省 26.90%','FontSize',11,'FontWeight','bold','Color',C.soc);
b=ax(f,[.73 .24 .235 .60]);panel(b,'b','往返效率响应');plot(b,D.q1_efficiency,D.q1_sensitivity,'-o','Color',C.grid,'MarkerFaceColor','w','MarkerSize',4);
scatter(b,81,D.q1_sensitivity(3),42,C.soc,'filled');text(b,80,4.03,'81% 主设定','FontSize',8,'Color',C.soc);
set(b,'XLim',[60 103],'YLim',[3.1 4.2],'XTick',[64 81 100]);xlabel(b,'往返效率 / %');ylabel(b,'最优日费用 / 万元');saveout(f,out,'q1_efficiency');

% UpSet-inspired dot matrix + aligned lollipops, with the final strategy path below.
f=fig(4.1);a=ax(f,[.10 .42 .19 .43]);panel(a,'a','预报组合');bits=[bitget((0:7)',1),bitget((0:7)',2),bitget((0:7)',3)];
for k=1:8
 scatter(a,1:3,repmat(k,1,3),15,[.87 .88 .90],'filled');on=find(bits(k,:));
 if numel(on)>1,plot(a,on,repmat(k,size(on)),'Color',C.grid,'LineWidth',1);end
 scatter(a,on,repmat(k,size(on)),22,C.grid,'filled');
end
set(a,'XLim',[.5 3.5],'YLim',[.5 8.5],'YDir','reverse','XTick',1:3,'XTickLabel',{'06','12','18'},'YTick',1:8,'YTickLabel',{'无','6','12','6+12','18','6+18','12+18','全部'});a.YGrid='off';xlabel(a,'日内更新 / h');
b=ax(f,[.43 .42 .51 .43]);panel(b,'b','相对仅午夜预报的节省');saving=D.q3_cost(1)-D.q3_cost;
for k=1:8,plot(b,[0 saving(k)],[k k],'-','Color',C.pale,'LineWidth',1.5);scatter(b,saving(k),k,25,C.grid,'filled');text(b,saving(k)+3,k,sprintf('%.2f',saving(k)),'FontSize',7.5);end
set(b,'YLim',[.5 8.5],'YDir','reverse','YTick',[],'XLim',[0 180],'XTick',0:50:150);b.YGrid='off';b.XGrid='on';xlabel(b,'全年节省 / 万元');
c=ax(f,[.13 .115 .78 .14]);panel(c,'c','最终策略的费用递进');plot(c,1:3,D.q3_evolution,'-o','Color',C.soc,'MarkerFaceColor','w','MarkerSize',4);
for k=1:3,text(c,k,D.q3_evolution(k)+2,sprintf('%.2f',D.q3_evolution(k)),'HorizontalAlignment','center','FontSize',8);end
set(c,'XLim',[.8 3.2],'YLim',[1344 1364],'YTick',[1345 1355 1365],'XTick',1:3,'XTickLabel',{'基础滚动','负载修正选择','库存价值控制'});ylabel(c,'费用 / 万元');saveout(f,out,'q3_updates');

% Price variability and the time structure relevant to storage.
f=fig(3.3);a=ax(f,[.10 .46 .79 .40]);panel(a,'a','全年实际电价');imagesc(a,1:365,D.hours,D.price');axis(a,'xy');
set(a,'XLim',[.5 365.5],'YLim',[0 24],'YTick',0:6:24,'XTick',[1 60 121 182 244 305],'XTickLabel',{'1月','3月','5月','7月','9月','11月'});ylabel(a,'时刻 / h');a.YGrid='off';
colormap(a,ramp([hex('#FDF9EE');C.gold;C.orange;C.emergency],128));clim(a,[0 1.85]);cb=colorbar(a,'Position',[.92 .46 .015 .40]);cb.Label.String='元/kWh';cb.FontSize=7.5;
b=ax(f,[.10 .14 .79 .16]);panel(b,'b','月均价格及10%—90%分位范围');months=month(datetime(2025,1,1)+days(0:364));m=zeros(1,12);lo=m;hi=m;
for k=1:12,z=D.price(months==k,:);m(k)=mean(z,'all');lo(k)=quantile(z(:),.1);hi(k)=quantile(z(:),.9);end
errorbar(b,1:12,m,m-lo,hi-m,'o','Color',C.price,'LineStyle','none','MarkerFaceColor',C.price,'MarkerSize',3,'CapSize',3);
set(b,'XLim',[.5 12.5],'XTick',1:12,'YLim',[0 1.8],'YTick',[0 .8 1.6]);xlabel(b,'月份');ylabel(b,'元/kWh');saveout(f,out,'annual_price');

% Historical residual ranges show uncertainty without a model competition.
f=fig(3.8);dates={'3月20日','6月21日','9月23日','12月21日'};
for k=1:4
 row=floor((k-1)/2);col=mod(k-1,2);a=ax(f,[.105+col*.48 .59-row*.43 .36 .27]);panel(a,char('a'+k-1),dates{k});
 fill(a,[D.hours fliplr(D.hours)],[D.specified_lower(k,:) fliplr(D.specified_upper(k,:))],C.pale,'FaceAlpha',.38,'EdgeColor','none');
 plot(a,D.hours,D.specified_forecast(k,:),'--','Color',C.grid,'LineWidth',1);
 plot(a,D.hours,D.specified_price(k,:),'-','Color',C.price,'LineWidth',.9);
 set(a,'XLim',[0 24],'XTick',0:6:24,'YLim',[0 1.9],'YTick',[0 .6 1.2 1.8]);ylabel(a,'电价 / 元每kWh');if row==1,xlabel(a,'时刻 / h');end
 if k==1,lg=legend(a,{'历史残差范围','零点预测','实际价格'},'Orientation','horizontal','Box','off','FontSize',7.5);lg.Position=[.18 .925 .70 .05];end
end
saveout(f,out,'price_uncertainty');

% One mechanism figure: realized price and storage actions share the time axis.
f=fig(3.85);k=3;a=ax(f,[.10 .71 .85 .18]);panel(a,'a','9月23日：实际电价与午夜预测');plot(a,D.hours,D.specified_price(k,:),'-','Color',C.price,'LineWidth',1);
plot(a,D.hours,D.specified_forecast(k,:),'--','Color',C.grid,'LineWidth',.9);ylabel(a,'元/kWh');set(a,'XLim',[0 24],'XTick',0:6:24,'XTickLabel',[]);
b=ax(f,[.10 .40 .85 .19]);panel(b,'b','储能状态随价格与供需变化');plot(b,D.hours,D.dayahead_soc_start_kwh(k,:)/1e3,'--','Color',C.base,'LineWidth',1.1);
plot(b,D.hours,D.rolling_soc_start_kwh(k,:)/1e3,'-','Color',C.soc,'LineWidth',1.25);ylabel(b,'储电量 / MWh');set(b,'XLim',[0 24],'XTick',0:6:24,'XTickLabel',[],'YLim',[0 12],'YTick',[1.2 6 10.8]);
legend(b,{'日前','滚动'},'Orientation','horizontal','Location','northwest','Box','off','FontSize',7.5);
c=ax(f,[.10 .12 .85 .17]);panel(c,'c','紧急补购：日前与滚动');stairs(c,D.hours,D.dayahead_emergency_kwh(k,:),'Color',C.base,'LineWidth',.85);
stairs(c,D.hours,D.rolling_emergency_kwh(k,:),'Color',C.emergency,'LineWidth',1);ylabel(c,'电量 / kWh');xlabel(c,'时刻 / h');set(c,'XLim',[0 24],'XTick',0:6:24);
for aa=[a b c],for h=[6 12 18],xline(aa,h,':','Color',[.7 .7 .7],'LineWidth',.6,'HandleVisibility','off');end,end
saveout(f,out,'price_dispatch');

% Keep only the two deployed strategies and the inventory-value evidence.
f=fig(2.65);a=ax(f,[.14 .28 .43 .48]);panel(a,'a','库存价值控制的月度节省');imagesc(a,2:12,1:2,D.q4_month_savings);
set(a,'YDir','reverse','YLim',[.5 2.5],'XLim',[1.5 12.5],'XTick',2:2:12,'YTick',[1 2],'YTickLabel',{'日前','滚动'});a.YGrid='off';xlabel(a,'月份');
colormap(a,ramp([1 1 1;hex('#B7B7EB');C.soc],128));clim(a,[0 3]);cb=colorbar(a,'Position',[.59 .28 .013 .48]);cb.FontSize=7;cb.Label.String='万元';
b=ax(f,[.75 .28 .20 .48]);panel(b,'b','全年节省及95%区间');
for k=1:2,plot(b,D.q4_ci(k,:),[k k],'-','Color',C.soc,'LineWidth',1);scatter(b,D.q4_savings(k),k,28,C.soc,'filled');text(b,D.q4_savings(k),k-.24,sprintf('%.3f',D.q4_savings(k)),'HorizontalAlignment','center','Color',C.soc,'FontSize',8);end
set(b,'YDir','reverse','YLim',[.5 2.5],'YTick',[1 2],'YTickLabel',{'日前','滚动'},'XScale','log','XLim',[.1 30],'XTick',[.1 1 10],'XTickLabel',{'0.1','1','10'});b.YGrid='off';b.XGrid='on';xlabel(b,'节省 / 万元（对数）');saveout(f,out,'inventory_savings');
disp('V7 MATLAB figures complete');
end

function f=fig(h)
f=figure('Visible','off','Color','w','Units','inches','Position',[1 1 6.10 h]);
set(f,'DefaultAxesFontName','Microsoft YaHei','DefaultTextFontName','Microsoft YaHei','DefaultAxesFontSize',8,'DefaultTextFontSize',8,'DefaultTextInterpreter','none','DefaultLegendInterpreter','none','DefaultAxesTickLabelInterpreter','none');
end
function a=ax(f,p)
a=axes(f,'Position',p);hold(a,'on');set(a,'FontSize',8,'LineWidth',.6,'TickDir','out','Box','off','YGrid','on','GridColor',[.82 .84 .86],'GridAlpha',.35,'Layer','top');
end
function panel(a,k,t)
text(a,0,1.14,[k '  ' t],'Units','normalized','FontWeight','bold','FontSize',8.3,'VerticalAlignment','bottom');
end
function c=hex(s),c=sscanf(s(2:end),'%2x%2x%2x',[1 3])/255;end
function m=ramp(c,n),m=interp1(linspace(0,1,size(c,1)),c,linspace(0,1,n));end
function box(a,p,t,c)
rectangle(a,'Position',p,'EdgeColor',c,'FaceColor','w','LineWidth',.8);text(a,p(1)+p(3)/2,p(2)+p(4)/2,t,'HorizontalAlignment','center','VerticalAlignment','middle','FontSize',8.1);
end
function arrow(a,p,q)
plot(a,[p(1) q(1)],[p(2) q(2)],'-','Color',[.3 .3 .3],'LineWidth',.6);v=(q-p)/norm(q-p);n=[-v(2) v(1)];u=q-1.1*v;patch(a,[q(1) u(1)+.45*n(1) u(1)-.45*n(1)],[q(2) u(2)+.45*n(2) u(2)-.45*n(2)],[.3 .3 .3],'EdgeColor','none');
end
function saveout(f,out,name)
drawnow;issues=audit_publication_figure(f);fid=fopen(fullfile(out,[name '_audit.json']),'w','n','UTF-8');fwrite(fid,jsonencode(issues),'char');fclose(fid);
export_publication_figure(f,string(fullfile(out,name)),600,true,false);exportgraphics(f,fullfile(out,[name '.pdf']),'ContentType','vector');savefig(f,fullfile(out,[name '.fig']));close(f);disp(['Exported ' name]);
end
