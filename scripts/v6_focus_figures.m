function v6_focus_figures(root,skillRoot)
% Second visual design: mechanisms rather than a cosmetic change of chart type.
cd(root);addpath(fullfile(skillRoot,'references','roles','编程手','scripts'));
D=load('artifacts/v6/figure_data.mat');C=[.302 .467 .608];G=[.502 .455 .784];B=[.616 .620 .639];
out='figures/v6';
f=newfig(2.85);a=axes(f,'Position',[.12 .23 .83 .67]);sty(a);hold(a,'on');
s=readmatrix('artifacts/v3/q1_efficiency.csv');x=s(:,2)*100;y=s(:,3)/1e4;base=D.q1_cost(1);
fill(a,[x;flipud(x)],[y;repmat(base,size(y))],C,'FaceAlpha',.13,'EdgeColor','none');
plot(a,[62 102],[base base],'--','Color',B,'LineWidth',1);
plot(a,x,y,'-o','Color',C,'LineWidth',1.5,'MarkerFaceColor','w','MarkerSize',4);
plot(a,[81 81],[3.0 base],':','Color',G,'LineWidth',.8);
scatter(a,81,y(3),55,G,'filled');scatter(a,90,y(4),35,C,'s','filled');
text(a,65,base+.11,'无储能  4.805万元','Color',[.35 .35 .35],'FontSize',8.5);
text(a,68,4.23,{'储能降低购电费用','主模型节省26.90%'},'Color',C,'FontSize',9.5);
text(a,82,3.70,{'主模型  往返81%','35,126.85元'},'FontSize',8,'Color',G);
text(a,92,3.72,{'往返90%','33,801.48元'},'FontSize',8,'Color',C);
set(a,'XLim',[62 103],'YLim',[3 5.15],'XTick',[64 72.25 81 90 100],'XTickLabel',{'64','72.25','81','90','100'});
xlabel(a,'充放电往返效率 / %');ylabel(a,'单日购电费用 / 万元');saveout(f,out,'q1_efficiency');

f=newfig(3.15);a=axes(f,'Position',[.12 .20 .83 .72]);sty(a);hold(a,'on');
normal=D.validation_cost-D.validation_emergency; col=[B;C];labels={'0','70%','80%','90%'};
for total=[51 60 70],xx=[44 72];plot(a,xx,total-xx,':','Color',[.82 .84 .87],'LineWidth',.8);end
for k=1:2
 plot(a,normal(k,:),D.validation_emergency(k,:),'-','Color',col(k,:),'LineWidth',1.2);
 for j=1:4
  mark='o';if k==2,mark='s';end
  scatter(a,normal(k,j),D.validation_emergency(k,j),32,col(k,:),mark,'filled');
  dx=.4;dy=.7;if k==2 && j==2,dx=-1.3;dy=-1.1;end
  text(a,normal(k,j)+dx,D.validation_emergency(k,j)+dy,labels{j},'FontSize',8,'Color',col(k,:));
 end
end
scatter(a,normal(2,2),D.validation_emergency(2,2),110,C,'o','LineWidth',1.1);
plot(a,[normal(2,2)+.35 54],[D.validation_emergency(2,2)+.3 4.1],'-','Color',C,'LineWidth',.6);
text(a,54.2,4.7,{'岭回归70%余量','验证总费50.98万元'},'Color',C,'FontSize',9,'BackgroundColor','w','Margin',2);
text(a,46.7,19.1,'同期预测','Color',[.38 .38 .38],'FontSize',9);
text(a,44.4,8.5,'岭回归','Color',C,'FontSize',9);
text(a,61.8,8.8,'总费70万元','Color',[.55 .55 .55],'FontSize',7.5,'Rotation',-31);
set(a,'XLim',[44 72],'YLim',[-2 20],'XTick',45:5:70,'YTick',0:5:20);
xlabel(a,'普通计划购电费 / 万元');ylabel(a,'紧急购电费 / 万元');
saveout(f,out,'q2_validation');

f=newfig(3.45);a=axes(f,'Position',[.12 .38 .83 .51]);sty(a);hold(a,'on');
% The sequential path isolates actual component substitutions; costs not summed across questions.
tot=sum(D.q2_cost,2);vals=tot([1 2 4 5]);xx=1:4;
for k=1:3
 fill(a,[k k+1 k+1 k],[vals(k) vals(k+1) 1320 1320],C,'FaceAlpha',.06+.035*k,'EdgeColor','none');
 plot(a,[k k+1],[vals(k) vals(k+1)],'-','Color',C,'LineWidth',1.5);
end
scatter(a,xx,vals,42,[B;C;C;G],'filled');
for k=1:4
text(a,k,vals(k)+28,sprintf('%.2f',vals(k)),'HorizontalAlignment','center','VerticalAlignment','bottom','FontSize',9);
end
set(a,'XLim',[.7 4.4],'YLim',[1320 2050],'YTick',[1400 1600 1800 2000],'XTick',1:4,'XTickLabel',{'同期无余量','岭回归预测','增加70%余量','库存价值控制'},'FontSize',8);
ylabel(a,'334天购电费用 / 万元');
text(a,.02,1.12,'a  逐层改进的实际费用','Units','normalized','FontWeight','bold','FontSize',9);
b=axes(f,'Position',[.12 .10 .83 .15]);axis(b,[0 1 0 1]);axis(b,'off');hold(b,'on');
head={'预测改善','风险校准','库存配置'};saving=-diff(vals);
for k=1:3
  left=(k-1)/3;
  if k>1,plot(b,[left-.02 left-.02],[.05 .95],'-','Color',[.86 .88 .90],'LineWidth',.7);end
  text(b,left+.02,.88,head{k},'FontSize',8.5,'Color',[.35 .35 .35]);
  color=C;if k==3,color=G;end
  text(b,left+.02,.35,sprintf('节省 %.2f 万元',saving(k)),'FontSize',10,'Color',color);
end
saveout(f,out,'q2_cost');disp('Three focused figures redesigned.');
end
function f=newfig(h)
f=figure('Visible','off','Color','w','Units','inches','Position',[1 1 6.3 h]);
set(f,'DefaultAxesFontName','Microsoft YaHei','DefaultTextFontName','Microsoft YaHei','DefaultTextInterpreter','none','DefaultAxesTickLabelInterpreter','none');
end
function sty(a)
set(a,'FontSize',8.5,'LineWidth',.65,'TickDir','out','Box','off','YGrid','on','GridColor',[.82 .85 .89],'GridAlpha',.45,'Layer','bottom');
end
function saveout(f,out,name)
issues=audit_publication_figure(f);fid=fopen(fullfile(out,[name '_audit.json']),'w','n','UTF-8');fwrite(fid,jsonencode(issues));fclose(fid);
export_publication_figure(f,string(fullfile(out,name)),360,true,false);
exportgraphics(f,fullfile(out,[name '.pdf']),'ContentType','vector');savefig(f,fullfile(out,[name '.fig']));close(f);
end
